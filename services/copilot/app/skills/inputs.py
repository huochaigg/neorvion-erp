from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.core.exceptions import AppError
from app.mcp.security import validate_arguments


@dataclass(frozen=True, slots=True)
class InputCollection:
    values: dict[str, Any]
    missing: tuple[str, ...]
    clarification: str | None

    @property
    def ready(self) -> bool:
        return not self.missing


class SkillInputCollector:
    """按 JSON Schema 属性提取确定性参数，并合并已确认值；不会让模型补造必填项。"""

    _cancel = re.compile(r"^(?:取消|算了|停止|不用了|cancel)[！!。.\s]*$", re.I)

    def collect(
        self,
        task: str,
        schema: dict[str, Any],
        previous: dict[str, Any] | None = None,
        *,
        today: date | None = None,
    ) -> InputCollection:
        values = dict(previous or {})
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        current = today or self.business_today()
        for name, spec in properties.items():
            extracted = self._extract(name, spec if isinstance(spec, dict) else {}, task, current)
            if name.lower() == "query" and name in values and self._supplement_only(task):
                extracted = None
            if extracted is not None:
                values[name] = extracted
        required = tuple(str(item) for item in schema.get("required", []) if isinstance(item, str))
        missing = tuple(name for name in required if values.get(name) in (None, "", []))
        if not missing:
            validate_arguments(schema, values)
        return InputCollection(values, missing, self._question(missing, properties) if missing else None)

    def cancelled(self, task: str) -> bool:
        return bool(self._cancel.fullmatch(task.strip()))

    @staticmethod
    def business_today() -> date:
        """用显式业务时区计算相对日期，避免部署主机时区导致日期漂移。"""
        try:
            return datetime.now(ZoneInfo(settings.skill_business_timezone)).date()
        except ZoneInfoNotFoundError as exc:
            raise AppError("Skill 业务时区配置无效", code=50089, status_code=500) from exc

    @staticmethod
    def _supplement_only(task: str) -> bool:
        text = task.strip()
        return bool(
            re.fullmatch(
                r"(?:最近|近)\s*\d{1,3}\s*天[！!。.\s]*|\d{4}-\d{2}-\d{2}(?:\s*(?:到|至|~)\s*\d{4}-\d{2}-\d{2})?[！!。.\s]*|(?:知识库|KB)\s*(?:ID)?\s*[：:#-]?\s*\d+[！!。.\s]*",
                text,
                re.I,
            )
        )

    def _extract(self, name: str, spec: dict[str, Any], task: str, today: date) -> Any:
        lowered = name.lower()
        if lowered in {"sku", "sku_code"}:
            match = re.search(r"\bSKU[-_A-Za-z0-9]+\b", task, re.I)
            return match.group(0) if match else None
        if lowered in {"start_date", "end_date"}:
            dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", task)
            if dates:
                return dates[0 if lowered == "start_date" else min(1, len(dates) - 1)]
            relative = re.search(r"(?:最近|近)\s*(\d{1,3})\s*天", task)
            if relative and 1 <= int(relative.group(1)) <= 366:
                end = today
                start = end - timedelta(days=int(relative.group(1)) - 1)
                return (start if lowered == "start_date" else end).isoformat()
            return None
        if lowered == "query":
            return task.strip() if len(task.strip()) >= int(spec.get("minLength", 1)) else None
        if lowered in {"knowledge_base_ids", "knowledge_base_id"}:
            ids = [int(item) for item in re.findall(r"(?:知识库|\bKB)\s*(?:id)?\s*[：:#-]?\s*(\d+)", task, re.I)]
            if not ids:
                return None
            return list(dict.fromkeys(ids)) if spec.get("type") == "array" else ids[0]
        if lowered in {"warehouse_id", "order_id", "product_id", "supplier_id"}:
            labels = {
                "warehouse_id": r"(?:仓库|warehouse)",
                "order_id": r"(?:订单主键|order[_\s-]*id|\bSO[-_])",
                "product_id": r"(?:商品|product)",
                "supplier_id": r"(?:供应商|supplier)",
            }
            match = re.search(labels[lowered] + r"\s*(?:id)?\s*[：:#-]?\D{0,3}(\d+)", task, re.I)
            return int(match.group(1)) if match else None
        if lowered == "top_k":
            return int(spec.get("default", 5))
        return None

    @staticmethod
    def _question(missing: tuple[str, ...], properties: dict[str, Any]) -> str:
        labels = []
        for name in missing:
            spec = properties.get(name)
            description = spec.get("description") if isinstance(spec, dict) else None
            labels.append(str(description or name))
        if set(missing) >= {"start_date", "end_date"}:
            return "请补充分析时间范围，例如“最近30天”或明确的开始、结束日期。"
        return "请补充以下必填参数：" + "；".join(labels) + "。"
