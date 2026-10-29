from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_chat_adapter
from app.ai.types import ModelMessage, ModelUsage
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.erp.client import ErpApiClient
from app.insights.detectors import detect, detector_registry
from app.models.evaluation import ModelCall
from app.models.governance import AIGovernancePolicy
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
    InsightAnalysisResult,
    InsightEventOut,
    InsightNotificationOut,
    InsightRuleCreate,
    InsightRuleOut,
    InsightRulePatch,
    InsightRunOut,
)
from app.schemas.workflow import WorkflowType
from app.services.quotas import enforce_runtime_governance, reserve_chat_quota, usage_tokens


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
        return await self._execute_detection(rule, run, now)

    async def execute_queued(self, run_id: int) -> InsightRunOut:
        """执行已由 Worker 领取的周期任务；规则停用或授权撤销时拒绝继续。"""
        run = await self.session.scalar(
            select(InsightDetectionRun).where(
                InsightDetectionRun.tenant_id == self.context.tenant_id,
                InsightDetectionRun.id == run_id,
            )
        )
        if run is None:
            raise AppError("检测运行不存在", code=40496, status_code=404)
        rule = await self._rule(run.rule_id)
        if not rule.enabled:
            raise AppError("检测规则已停用", code=40997, status_code=409)
        self._require_permissions(detector_registry.get(rule.detector_type).required_permissions)
        return await self._execute_detection(rule, run, run.started_at or datetime.now(UTC))

    async def _execute_detection(
        self, rule: InsightRule, run: InsightDetectionRun, now: datetime
    ) -> InsightRunOut:
        """执行确定性检测并提交结果；外部请求期间不持有数据库行锁。"""
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
            run.lease_owner = None
            run.lease_until = None
            rule.next_run_at = (
                now + timedelta(minutes=rule.interval_minutes) if rule.enabled else None
            )
            await self.session.commit()
        except AppError as exc:
            await self.session.rollback()
            failed_run = await self.session.scalar(
                select(InsightDetectionRun)
                .where(
                    InsightDetectionRun.tenant_id == self.context.tenant_id,
                    InsightDetectionRun.id == run.id,
                )
                .with_for_update()
            )
            if failed_run is not None:
                (
                    failed_run.status,
                    failed_run.error_code,
                    failed_run.safe_error,
                    failed_run.finished_at,
                ) = (
                    "FAILED",
                    exc.code,
                    exc.message[:255],
                    datetime.now(UTC),
                )
                failed_run.lease_owner = None
                failed_run.lease_until = None
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

    async def chat_seed(self, insight_id: int) -> tuple[BusinessInsight, str]:
        """把授权后的结构化洞察压缩为安全首问，不携带隐藏 Prompt 或任意指令。"""
        row = await self._insight(insight_id)
        evidence = row.evidence_summary or {}
        allowed = {
            key: evidence[key]
            for key in (
                "available_quantity",
                "threshold",
                "warehouse_id",
                "sku_id",
                "sku_code",
                "expected_arrival_date",
                "overdue_days",
                "processing_sla_hours",
                "status",
                "coverage_days",
                "threshold_days",
                "observed_at",
            )
            if key in evidence
        }
        prompt = (
            f"请分析主动洞察 #{row.id}（{row.detector_type}，严重度 {row.severity}）。"
            f"只基于以下已验证事实回答，区分事实、规则、推断和信息不足：{allowed}"
        )
        return row, prompt[:4000]

    async def workflow_seed(
        self, insight_id: int
    ) -> tuple[BusinessInsight, WorkflowType, dict[str, Any]]:
        """仅把固定 Detector 映射到现有白名单 Workflow，不允许模型选择工作流或参数。"""
        row = await self._insight(insight_id)
        evidence = row.evidence_summary or {}
        if row.detector_type in {"LOW_STOCK_RISK", "INVENTORY_COVERAGE_RISK"}:
            sku_code = str(evidence.get("sku_code") or "").strip()
            if not sku_code and row.detector_type == "INVENTORY_COVERAGE_RISK":
                sku_code = row.resource_id.split(":", 1)[-1].strip()
            if not sku_code:
                raise AppError("洞察缺少 SKU，不能启动补货工作流", code=40998, status_code=409)
            workflow_type: WorkflowType = "INVENTORY_REPLENISHMENT_WORKFLOW"
            values: dict[str, Any] = {"sku_code": sku_code}
            warehouse = evidence.get("warehouse_id")
            if warehouse is not None:
                values["warehouse_id"] = int(warehouse)
        elif row.detector_type == "OVERDUE_SHIPMENT":
            try:
                order_id = int(row.resource_id)
            except ValueError as exc:
                raise AppError("洞察订单标识无效", code=40998, status_code=409) from exc
            workflow_type = "SALES_ORDER_REVIEW_WORKFLOW"
            values = {"order_id": order_id}
        else:
            raise AppError("当前洞察没有安全的工作流映射", code=40998, status_code=409)
        return row, workflow_type, values

    async def record_link(self, insight_id: int, event_type: str, target_id: int) -> None:
        await self._insight(insight_id)
        self._event(insight_id, event_type, self.context.user_id, {"target_id": target_id})
        await self.session.commit()

    async def analyze(self, insight_id: int) -> BusinessInsightOut:
        """在无工具模型调用中分析已验证证据；模型失败不影响原始告警事实。"""
        row = await self._insight(insight_id, lock=True)
        policy = await self.session.scalar(
            select(AIGovernancePolicy).where(AIGovernancePolicy.tenant_id == self.context.tenant_id)
        )
        if policy is None or not policy.insight_analysis_enabled:
            raise AppError("租户未启用 AI 洞察分析", code=40376, status_code=403)
        if (
            policy.allowed_provider_codes
            and settings.model_provider not in policy.allowed_provider_codes
        ):
            raise AppError("当前模型 Provider 不符合租户策略", code=40377, status_code=403)
        if policy.allowed_model_names and settings.chat_model not in policy.allowed_model_names:
            raise AppError("当前模型不符合租户策略", code=40377, status_code=403)
        await enforce_runtime_governance(self.session, self.context.tenant_id, "INSIGHT_ANALYSIS")
        row.analysis_status = "RUNNING"
        await self.session.commit()

        evidence_json = json.dumps(row.evidence_summary, ensure_ascii=False, default=str)[:6000]
        messages: list[ModelMessage] = [
            {
                "role": "system",
                "content": (
                    "你是企业 ERP 洞察分析器。只能依据输入事实，不得调用工具、不得建议自动写入。"
                    "严格输出 JSON：fact_summary、rule_basis、inference、"
                    "insufficient_information、recommendations。recommendations 仅提供人工复核建议。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"detector={row.detector_type}; severity={row.severity}; "
                    f"resource={row.resource_type}:{row.resource_id}; evidence={evidence_json}"
                ),
            },
        ]
        reservation = await reserve_chat_quota(
            self.session,
            self.context.tenant_id,
            max(1, (len(evidence_json) + 2) // 3) + settings.chat_max_output_tokens,
        )
        started = perf_counter()
        call = ModelCall(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            request_id=self.request_id[:64],
            model_call_id=uuid.uuid4().hex,
            model_provider=settings.model_provider,
            model_name=settings.chat_model,
            status="RUNNING",
        )
        model_call_id = call.model_call_id
        self.session.add(call)
        await self.session.commit()
        usage: ModelUsage | None = None
        try:
            chunks: list[str] = []
            async for delta in get_chat_adapter().stream(messages):
                if delta.text:
                    chunks.append(delta.text)
                if delta.usage is not None:
                    usage = delta.usage
            payload = self._analysis_json("".join(chunks))
            result = InsightAnalysisResult.model_validate(payload)
            row = await self._insight(insight_id, lock=True)
            row.ai_summary = result.fact_summary
            row.recommendations = [
                {
                    "rule_basis": result.rule_basis,
                    "inference": result.inference,
                    "insufficient_information": result.insufficient_information,
                },
                *result.recommendations,
            ][:5]
            row.analysis_status = "SUCCEEDED"
            call.status = "SUCCEEDED"
            call.completed_at = datetime.now(UTC)
            call.duration_ms = int((perf_counter() - started) * 1000)
            call.input_tokens = usage.get("prompt_tokens") if usage else None
            call.output_tokens = usage.get("completion_tokens") if usage else None
            call.usage_source = "PROVIDER" if usage_tokens(usage) is not None else "UNKNOWN"
            self._event(row.id, "INSIGHT_ANALYZED", self.context.user_id, {})
            await self.session.commit()
            await reservation.settle(usage_tokens(usage))
            return BusinessInsightOut.model_validate(row)
        except Exception as exc:
            await self.session.rollback()
            row = await self._insight(insight_id, lock=True)
            row.analysis_status = "FAILED"
            call = await self.session.scalar(
                select(ModelCall).where(
                    ModelCall.tenant_id == self.context.tenant_id,
                    ModelCall.model_call_id == model_call_id,
                )
            )
            if call is not None:
                call.status = "FAILED"
                call.completed_at = datetime.now(UTC)
                call.duration_ms = int((perf_counter() - started) * 1000)
                call.error_code = exc.code if isinstance(exc, AppError) else 50268
            self._event(row.id, "INSIGHT_ANALYSIS_FAILED", self.context.user_id, {})
            await self.session.commit()
            await reservation.cancel()
            if isinstance(exc, AppError):
                raise
            raise AppError("洞察分析输出无效", code=50298, status_code=502) from exc

    @staticmethod
    def _analysis_json(value: str) -> dict[str, Any]:
        """只接受单一 JSON 对象，兼容常见 Markdown fence 但拒绝其余自由文本。"""
        text_value = value.strip()
        if text_value.startswith("```") and text_value.endswith("```"):
            lines = text_value.splitlines()
            text_value = "\n".join(lines[1:-1]).strip()
        try:
            parsed = json.loads(text_value)
        except json.JSONDecodeError as exc:
            raise AppError("洞察分析输出不是有效 JSON", code=50298, status_code=502) from exc
        if not isinstance(parsed, dict):
            raise AppError("洞察分析输出必须是 JSON 对象", code=50298, status_code=502)
        return parsed

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
