from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.exceptions import AppError


class LowStockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warehouse_id: int | None = Field(default=None, gt=0)
    sku_code: str | None = Field(default=None, min_length=1, max_length=64)
    threshold: int = Field(ge=0, le=1_000_000)


class PurchaseDelayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warehouse_id: int | None = Field(default=None, gt=0)
    grace_days: int = Field(default=0, ge=0, le=30)


class ShipmentSlaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warehouse_id: int | None = Field(default=None, gt=0)
    processing_sla_hours: int = Field(ge=1, le=720)


class CoverageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_code: str = Field(min_length=1, max_length=64)
    warehouse_id: int | None = Field(default=None, gt=0)
    lookback_days: int = Field(default=30, ge=7, le=365)
    minimum_coverage_days: Decimal = Field(gt=0, le=Decimal("365"))


@dataclass(frozen=True)
class DetectorSpec:
    detector_type: str
    version: str
    description: str
    config_model: type[BaseModel]
    required_permissions: tuple[str, ...]
    enabled: bool = True
    maximum_result_count: int = 500


class DetectorRegistry:
    def __init__(self) -> None:
        self._specs = {
            "LOW_STOCK_RISK": DetectorSpec(
                "LOW_STOCK_RISK",
                "1.0",
                "可用库存低于正式规则阈值",
                LowStockConfig,
                ("inventory:read",),
            ),
            "OVERDUE_SHIPMENT": DetectorSpec(
                "OVERDUE_SHIPMENT",
                "1.0",
                "订单超过租户配置的处理 SLA；不冒充承诺发货日期",
                ShipmentSlaConfig,
                ("order:read",),
            ),
            "PURCHASE_ARRIVAL_DELAY": DetectorSpec(
                "PURCHASE_ARRIVAL_DELAY",
                "1.0",
                "采购单超过真实预计到货日期且未收齐",
                PurchaseDelayConfig,
                ("purchase:read",),
            ),
            "INVENTORY_COVERAGE_RISK": DetectorSpec(
                "INVENTORY_COVERAGE_RISK",
                "1.0",
                "可用库存除以统计期日均有效销量",
                CoverageConfig,
                ("analytics:sales:read", "inventory:read"),
            ),
        }

    def get(self, detector_type: str) -> DetectorSpec:
        spec = self._specs.get(detector_type)
        if spec is None or not spec.enabled:
            raise AppError("检测器不存在或未启用", code=40091, status_code=400)
        return spec

    def validate(self, detector_type: str, config: dict[str, Any]) -> dict[str, Any]:
        try:
            return (
                self.get(detector_type).config_model.model_validate(config).model_dump(mode="json")
            )
        except ValidationError as exc:
            raise AppError(
                "检测规则配置无效",
                code=42291,
                status_code=422,
                data={"errors": exc.errors(include_url=False)},
            ) from exc

    def catalog(self) -> list[DetectorSpec]:
        return list(self._specs.values())


detector_registry = DetectorRegistry()


def fingerprint(detector_type: str, resource_type: str, resource_id: str) -> str:
    return hashlib.sha256(f"{detector_type}:{resource_type}:{resource_id}".encode()).hexdigest()


def detect(
    detector_type: str, config: dict[str, Any], data: dict[str, Any], *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """只执行固定确定性公式；输入必须来自固定 ERP API，永不解释 SQL 或模型输出。"""
    now = now or datetime.now(UTC)
    if detector_type == "LOW_STOCK_RISK":
        return _low_stock(config, data, now)
    if detector_type == "PURCHASE_ARRIVAL_DELAY":
        return _purchase_delay(config, data, now)
    if detector_type == "OVERDUE_SHIPMENT":
        return _shipment_sla(config, data, now)
    if detector_type == "INVENTORY_COVERAGE_RISK":
        return _coverage(config, data, now)
    raise AppError("检测器不存在", code=40091, status_code=400)


def _low_stock(config: dict[str, Any], data: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    threshold = int(config["threshold"])
    results = []
    for row in data.get("items", [])[:500]:
        available = int(
            row.get(
                "available_quantity",
                int(row.get("quantity", 0)) - int(row.get("reserved_quantity", 0)),
            )
        )
        if available >= threshold:
            continue
        rid = f"{row.get('warehouse_id')}:{row.get('sku_id')}"
        results.append(
            _result(
                "LOW_STOCK_RISK",
                "inventory",
                rid,
                "HIGH" if available <= 0 else "MEDIUM",
                {
                    "available_quantity": available,
                    "threshold": threshold,
                    "quantity": row.get("quantity"),
                    "reserved_quantity": row.get("reserved_quantity"),
                    "warehouse_id": row.get("warehouse_id"),
                    "sku_id": row.get("sku_id"),
                    "sku_code": row.get("sku_code"),
                    "observed_at": now.isoformat(),
                },
            )
        )
    return results


def _purchase_delay(
    config: dict[str, Any], data: dict[str, Any], now: datetime
) -> list[dict[str, Any]]:
    cutoff = now.date() - timedelta(days=int(config.get("grace_days", 0)))
    results = []
    for row in data.get("items", [])[:500]:
        raw = row.get("expected_arrival_date")
        if not raw or row.get("status") not in {"WAITING_RECEIPT", "PARTIALLY_RECEIVED"}:
            continue
        expected = date.fromisoformat(str(raw))
        if expected >= cutoff:
            continue
        results.append(
            _result(
                "PURCHASE_ARRIVAL_DELAY",
                "purchase_order",
                str(row.get("id")),
                "HIGH",
                {
                    "expected_arrival_date": expected.isoformat(),
                    "status": row.get("status"),
                    "overdue_days": (now.date() - expected).days,
                    "observed_at": now.isoformat(),
                },
            )
        )
    return results


def _shipment_sla(
    config: dict[str, Any], data: dict[str, Any], now: datetime
) -> list[dict[str, Any]]:
    hours = int(config["processing_sla_hours"])
    cutoff = now - timedelta(hours=hours)
    results = []
    for row in data.get("items", [])[:500]:
        created = (
            datetime.fromisoformat(str(row.get("created_at", "")).replace("Z", "+00:00"))
            if row.get("created_at")
            else None
        )
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if (
            not created
            or created >= cutoff
            or row.get("status")
            not in {"WAITING_OUTBOUND", "PARTIALLY_OUTBOUND", "OUTBOUNDED", "PARTIALLY_SHIPPED"}
        ):
            continue
        results.append(
            _result(
                "OVERDUE_SHIPMENT",
                "sales_order",
                str(row.get("id")),
                "MEDIUM",
                {
                    "basis": "PROCESSING_SLA",
                    "processing_sla_hours": hours,
                    "created_at": created.isoformat(),
                    "status": row.get("status"),
                    "observed_at": now.isoformat(),
                },
            )
        )
    return results


def _coverage(config: dict[str, Any], data: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    try:
        available = Decimal(str(data.get("available_quantity")))
        quantity = Decimal(str(data.get("sales_quantity")))
        days = Decimal(str(data.get("period_days")))
        threshold = Decimal(str(config["minimum_coverage_days"]))
        average = quantity / days if days > 0 else Decimal("0")
        coverage = None if average <= 0 else available / average
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AppError("覆盖分析数据无效", code=50292, status_code=502) from exc
    if coverage is None or coverage >= threshold:
        return []
    rid = f"{config.get('warehouse_id') or 'all'}:{config['sku_code']}"
    return [
        _result(
            "INVENTORY_COVERAGE_RISK",
            "inventory_coverage",
            rid,
            "HIGH" if coverage <= threshold / 2 else "MEDIUM",
            {
                "available_quantity": str(available),
                "sales_quantity": str(quantity),
                "period_days": int(days),
                "average_daily_sales": str(average),
                "coverage_days": str(coverage.quantize(Decimal("0.01"))),
                "threshold_days": str(threshold),
                "formula": "available_quantity / average_daily_sales",
                "observed_at": now.isoformat(),
            },
        )
    ]


def _result(
    kind: str, resource_type: str, resource_id: str, severity: str, evidence: dict[str, Any]
) -> dict[str, Any]:
    return {
        "detector_type": kind,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "fingerprint": fingerprint(kind, resource_type, resource_id),
        "severity": severity,
        "evidence_summary": json.loads(json.dumps(evidence, default=str)),
    }
