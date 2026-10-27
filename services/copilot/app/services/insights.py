from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.erp.client import ErpApiClient
from app.insights.detectors import detect, detector_registry
from app.models.insight import (
    BusinessInsight,
    InsightDetectionRun,
    InsightEvent,
    InsightNotification,
    InsightRule,
    InsightRuleRevision,
)
from app.schemas.insight import (
    BusinessInsightOut,
    InsightAction,
    InsightEventOut,
    InsightNotificationOut,
    InsightRuleCreate,
    InsightRuleOut,
    InsightRulePatch,
    InsightRunOut,
)


class InsightService:
    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        erp: ErpApiClient,
        access_token: str,
        request_id: str,
    ) -> None:
        self.session = session
        self.context = context
        self.erp = erp
        self.access_token = access_token
        self.request_id = request_id

    async def create_rule(self, payload: InsightRuleCreate) -> InsightRuleOut:
        spec = detector_registry.get(payload.detector_type)
        self._require_permissions(spec.required_permissions)
        config = detector_registry.validate(payload.detector_type, payload.config)
        self._timezone(payload.timezone)
        row = InsightRule(
            tenant_id=self.context.tenant_id,
            name=payload.name,
            detector_type=spec.detector_type,
            detector_version=spec.version,
            config=config,
            timezone=payload.timezone,
            interval_minutes=payload.interval_minutes,
            enabled=payload.enabled,
            severity_config=payload.severity_config,
            cooldown_seconds=payload.cooldown_seconds,
            max_alerts_per_run=payload.max_alerts_per_run,
            next_run_at=datetime.now(UTC) if payload.enabled else None,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(row)
        try:
            await self.session.flush()
            await self._revision(row)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("同名主动洞察规则已存在", code=40996, status_code=409) from exc
        return InsightRuleOut.model_validate(row)

    async def list_rules(self, page: int, page_size: int) -> dict[str, Any]:
        filters = (InsightRule.tenant_id == self.context.tenant_id,)
        total = int(
            await self.session.scalar(select(func.count()).select_from(InsightRule).where(*filters))
            or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    select(InsightRule)
                    .where(*filters)
                    .order_by(InsightRule.updated_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return {
            "items": [InsightRuleOut.model_validate(x) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def rule(self, rule_id: int) -> InsightRuleOut:
        return InsightRuleOut.model_validate(await self._rule(rule_id))

    async def patch_rule(self, rule_id: int, payload: InsightRulePatch) -> InsightRuleOut:
        row = await self._rule(rule_id, lock=True, owner_only=True)
        self._require_permissions(detector_registry.get(row.detector_type).required_permissions)
        values = payload.model_dump(exclude_unset=True)
        if "config" in values:
            values["config"] = detector_registry.validate(row.detector_type, values["config"])
        if "timezone" in values:
            self._timezone(values["timezone"])
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_by = self.context.user_id
        row.next_run_at = (
            datetime.now(UTC)
            if row.enabled and row.next_run_at is None
            else (None if not row.enabled else row.next_run_at)
        )
        await self._revision(row)
        await self.session.commit()
        return InsightRuleOut.model_validate(row)

    async def run_now(self, rule_id: int) -> InsightRunOut:
        """使用当前用户短期 Token 执行固定只读 ERP 查询；Token 不进入数据库或 Redis。"""
        rule = await self._rule(rule_id, owner_only=True)
        spec = detector_registry.get(rule.detector_type)
        self._require_permissions(spec.required_permissions)
        now = datetime.now(UTC)
        run = InsightDetectionRun(
            tenant_id=self.context.tenant_id,
            rule_id=rule.id,
            requested_by=self.context.user_id,
            schedule_key=f"manual:{self.context.user_id}:{now.isoformat()}",
            detector_version=rule.detector_version,
            rule_snapshot=self._snapshot(rule),
            status="RUNNING",
            started_at=now,
        )
        self.session.add(run)
        await self.session.commit()
        try:
            data = await self._fetch(rule)
            findings = detect(rule.detector_type, rule.config, data, now=now)[
                : rule.max_alerts_per_run
            ]
            created, duplicate = await self._persist_findings(rule, run, findings, now)
            run.detected_count = created + duplicate
            run.duplicate_count = duplicate
            run.status = "SUCCEEDED"
            run.finished_at = datetime.now(UTC)
            rule.next_run_at = (
                now + timedelta(minutes=rule.interval_minutes) if rule.enabled else None
            )
            await self.session.commit()
        except AppError as exc:
            await self.session.rollback()
            run = await self.session.scalar(
                select(InsightDetectionRun)
                .where(
                    InsightDetectionRun.tenant_id == self.context.tenant_id,
                    InsightDetectionRun.id == run.id,
                )
                .with_for_update()
            )
            if run is not None:
                run.status, run.error_code, run.safe_error, run.finished_at = (
                    "FAILED",
                    exc.code,
                    exc.message[:255],
                    datetime.now(UTC),
                )
                await self.session.commit()
            raise
        return InsightRunOut.model_validate(run)

    async def list_insights(
        self, page: int, page_size: int, status: str | None, severity: str | None
    ) -> dict[str, Any]:
        filters: list[Any] = [
            BusinessInsight.tenant_id == self.context.tenant_id,
            BusinessInsight.detector_type.in_(self._allowed_detector_types()),
        ]
        if status:
            filters.append(BusinessInsight.status == status)
        if severity:
            filters.append(BusinessInsight.severity == severity)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(BusinessInsight).where(*filters)
            )
            or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    select(BusinessInsight)
                    .where(*filters)
                    .order_by(BusinessInsight.last_seen_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return {
            "items": [BusinessInsightOut.model_validate(x) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def list_runs(self, page: int, page_size: int) -> dict[str, Any]:
        filters = (InsightDetectionRun.tenant_id == self.context.tenant_id,)
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(InsightDetectionRun).where(*filters)
            )
            or 0
        )
        rows = (
            await self.session.scalars(
                select(InsightDetectionRun)
                .where(*filters)
                .order_by(InsightDetectionRun.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return {
            "items": [InsightRunOut.model_validate(x) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def run_detail(self, run_id: int) -> InsightRunOut:
        row = await self.session.scalar(
            select(InsightDetectionRun).where(
                InsightDetectionRun.tenant_id == self.context.tenant_id,
                InsightDetectionRun.id == run_id,
            )
        )
        if row is None:
            raise AppError("检测运行不存在", code=40496, status_code=404)
        return InsightRunOut.model_validate(row)

    async def dashboard(self) -> dict[str, Any]:
        rows = (
            await self.session.execute(
                select(BusinessInsight.severity, func.count())
                .where(
                    BusinessInsight.tenant_id == self.context.tenant_id,
                    BusinessInsight.detector_type.in_(self._allowed_detector_types()),
                    BusinessInsight.status.in_(("OPEN", "ACKNOWLEDGED", "SNOOZED")),
                )
                .group_by(BusinessInsight.severity)
            )
        ).all()
        counts = {str(key): int(value) for key, value in rows}
        return {
            "open_total": sum(counts.values()),
            "severity": counts,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def insight(self, insight_id: int) -> BusinessInsightOut:
        return BusinessInsightOut.model_validate(await self._insight(insight_id))

    async def transition(
        self, insight_id: int, action: str, payload: InsightAction
    ) -> BusinessInsightOut:
        row = await self._insight(insight_id, lock=True)
        now = datetime.now(UTC)
        mapping = {"acknowledge": "ACKNOWLEDGED", "close": "CLOSED", "resolve": "RESOLVED"}
        if action == "snooze":
            if payload.snoozed_until is None or payload.snoozed_until <= now:
                raise AppError("延后时间必须晚于当前时间", code=42292, status_code=422)
            row.status, row.snoozed_until = "SNOOZED", payload.snoozed_until
        elif action in mapping:
            row.status = mapping[action]
            if action == "resolve":
                row.resolved_at = now
        else:
            raise AppError("Insight 状态操作无效", code=40092, status_code=400)
        self._event(row.id, f"INSIGHT_{row.status}", self.context.user_id, {})
        await self.session.commit()
        return BusinessInsightOut.model_validate(row)

    async def events(self, insight_id: int) -> list[InsightEventOut]:
        await self._insight(insight_id)
        rows = (
            await self.session.scalars(
                select(InsightEvent)
                .where(
                    InsightEvent.tenant_id == self.context.tenant_id,
                    InsightEvent.insight_id == insight_id,
                )
                .order_by(InsightEvent.created_at)
            )
        ).all()
        return [InsightEventOut.model_validate(x) for x in rows]

    async def notifications(self, page: int, page_size: int) -> dict[str, Any]:
        filters = (
            InsightNotification.tenant_id == self.context.tenant_id,
            InsightNotification.recipient_user_id == self.context.user_id,
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(InsightNotification).where(*filters)
            )
            or 0
        )
        rows = (
            await self.session.scalars(
                select(InsightNotification)
                .where(*filters)
                .order_by(InsightNotification.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return {
            "items": [InsightNotificationOut.model_validate(x) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def read_notification(self, notification_id: int) -> InsightNotificationOut:
        row = await self.session.scalar(
            select(InsightNotification).where(
                InsightNotification.tenant_id == self.context.tenant_id,
                InsightNotification.recipient_user_id == self.context.user_id,
                InsightNotification.id == notification_id,
            )
        )
        if row is None:
            raise AppError("通知不存在", code=40495, status_code=404)
        row.read_at = row.read_at or datetime.now(UTC)
        await self.session.commit()
        return InsightNotificationOut.model_validate(row)

    async def _fetch(self, rule: InsightRule) -> dict[str, Any]:
        common = {
            "access_token": self.access_token,
            "tenant_id": self.context.tenant_id,
            "request_id": self.request_id,
        }
        cfg = rule.config
        if rule.detector_type == "LOW_STOCK_RISK":
            params = {
                "page": 1,
                "page_size": min(rule.max_alerts_per_run, settings.tool_max_page_size),
            }
            if cfg.get("warehouse_id"):
                params["warehouse_id"] = cfg["warehouse_id"]
            if cfg.get("sku_code"):
                params["sku_code"] = cfg["sku_code"]
            return await self.erp.get("/api/v1/inventory", params=params, **common)
        if rule.detector_type == "PURCHASE_ARRIVAL_DELAY":
            params = {
                "page": 1,
                "page_size": min(rule.max_alerts_per_run, settings.tool_max_page_size),
                "expected_to": date.today().isoformat(),
            }
            if cfg.get("warehouse_id"):
                params["warehouse_id"] = cfg["warehouse_id"]
            return await self.erp.get("/api/v1/purchase-orders", params=params, **common)
        if rule.detector_type == "OVERDUE_SHIPMENT":
            cutoff = datetime.now(UTC) - timedelta(hours=cfg["processing_sla_hours"])
            params = {
                "page": 1,
                "page_size": min(rule.max_alerts_per_run, settings.tool_max_page_size),
                "created_to": cutoff.date().isoformat(),
            }
            if cfg.get("warehouse_id"):
                params["warehouse_id"] = cfg["warehouse_id"]
            return await self.erp.get("/api/v1/sales-orders", params=params, **common)
        end = date.today()
        start = end - timedelta(days=cfg["lookback_days"] - 1)
        sales = await self.erp.get(
            "/api/v1/analytics/sales/sku",
            params={
                "sku_code": cfg["sku_code"],
                "warehouse_id": cfg.get("warehouse_id"),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            **common,
        )
        inventory = await self.erp.get(
            "/api/v1/inventory",
            params={
                "sku_code": cfg["sku_code"],
                "warehouse_id": cfg.get("warehouse_id"),
                "page": 1,
                "page_size": settings.tool_max_page_size,
            },
            **common,
        )
        sales["available_quantity"] = sum(
            int(x.get("available_quantity", 0)) for x in inventory.get("items", [])
        )
        return sales

    async def _persist_findings(
        self,
        rule: InsightRule,
        run: InsightDetectionRun,
        findings: list[dict[str, Any]],
        now: datetime,
    ) -> tuple[int, int]:
        created = duplicate = 0
        for item in findings:
            row = await self.session.scalar(
                select(BusinessInsight)
                .where(
                    BusinessInsight.tenant_id == self.context.tenant_id,
                    BusinessInsight.rule_id == rule.id,
                    BusinessInsight.fingerprint == item["fingerprint"],
                )
                .with_for_update()
            )
            if row:
                row.last_seen_at = now
                row.detection_run_id = run.id
                row.evidence_summary = item["evidence_summary"]
                if row.status == "RESOLVED":
                    row.status = "OPEN"
                    row.resolved_at = None
                self._event(row.id, "INSIGHT_SEEN_AGAIN", None, {"run_id": run.id})
                duplicate += 1
                continue
            row = BusinessInsight(
                tenant_id=self.context.tenant_id,
                rule_id=rule.id,
                detection_run_id=run.id,
                detected_at=now,
                last_seen_at=now,
                analysis_status="NOT_REQUESTED",
                **item,
            )
            self.session.add(row)
            await self.session.flush()
            self._event(row.id, "INSIGHT_OPENED", None, {"run_id": run.id})
            self.session.add(
                InsightNotification(
                    tenant_id=self.context.tenant_id,
                    insight_id=row.id,
                    recipient_user_id=rule.created_by,
                    title=f"{item['severity']} · {rule.name}",
                    safe_body=f"检测到 {item['detector_type']}，请进入主动洞察查看授权详情。",
                    severity=item["severity"],
                )
            )
            created += 1
        return created, duplicate

    async def _revision(self, row: InsightRule) -> None:
        revision = (
            int(
                await self.session.scalar(
                    select(func.count())
                    .select_from(InsightRuleRevision)
                    .where(
                        InsightRuleRevision.tenant_id == self.context.tenant_id,
                        InsightRuleRevision.rule_id == row.id,
                    )
                )
                or 0
            )
            + 1
        )
        self.session.add(
            InsightRuleRevision(
                tenant_id=self.context.tenant_id,
                rule_id=row.id,
                revision=revision,
                snapshot=self._snapshot(row),
                changed_by=self.context.user_id,
            )
        )

    def _require_permissions(self, permissions: tuple[str, ...]) -> None:
        missing = [x for x in permissions if x not in self.context.permission_codes]
        if missing:
            raise AppError(
                "缺少检测所需只读权限", code=40391, status_code=403, data={"missing": missing}
            )

    async def _rule(
        self, rule_id: int, lock: bool = False, owner_only: bool = False
    ) -> InsightRule:
        stmt = select(InsightRule).where(
            InsightRule.tenant_id == self.context.tenant_id, InsightRule.id == rule_id
        )
        if owner_only:
            stmt = stmt.where(InsightRule.created_by == self.context.user_id)
        row = await self.session.scalar(stmt.with_for_update() if lock else stmt)
        if row is None:
            raise AppError("主动洞察规则不存在", code=40494, status_code=404)
        return row

    async def _insight(self, insight_id: int, lock: bool = False) -> BusinessInsight:
        stmt = select(BusinessInsight).where(
            BusinessInsight.tenant_id == self.context.tenant_id, BusinessInsight.id == insight_id
        )
        row = await self.session.scalar(stmt.with_for_update() if lock else stmt)
        if row is None:
            raise AppError("Insight 不存在", code=40495, status_code=404)
        self._require_permissions(detector_registry.get(row.detector_type).required_permissions)
        return row

    def _allowed_detector_types(self) -> list[str]:
        return [
            spec.detector_type
            for spec in detector_registry.catalog()
            if all(code in self.context.permission_codes for code in spec.required_permissions)
        ]

    def _event(
        self, insight_id: int, event_type: str, actor: int | None, summary: dict[str, Any]
    ) -> None:
        self.session.add(
            InsightEvent(
                tenant_id=self.context.tenant_id,
                insight_id=insight_id,
                event_type=event_type,
                actor_user_id=actor,
                safe_summary=summary,
            )
        )

    @staticmethod
    def _snapshot(row: InsightRule) -> dict[str, Any]:
        return {
            "name": row.name,
            "detector_type": row.detector_type,
            "detector_version": row.detector_version,
            "config": row.config,
            "timezone": row.timezone,
            "interval_minutes": row.interval_minutes,
            "enabled": row.enabled,
            "severity_config": row.severity_config,
            "cooldown_seconds": row.cooldown_seconds,
            "max_alerts_per_run": row.max_alerts_per_run,
        }

    @staticmethod
    def _timezone(value: str) -> None:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise AppError("时区名称无效", code=42293, status_code=422) from exc
