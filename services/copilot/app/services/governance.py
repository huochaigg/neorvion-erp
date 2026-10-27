from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.action_execution import ActionExecution
from app.models.agent_trace import AgentRun
from app.models.conversation import Conversation, ToolRun
from app.models.evaluation import AgentEvaluationRun, ModelCall
from app.models.governance import (
    AIGovernanceAudit,
    AIGovernancePolicy,
    AIModelDefinition,
    AIModelProvider,
    AIRetentionRun,
    TenantAIQuota,
)
from app.models.insight import InsightDetectionRun
from app.models.workflow import WorkflowInstance
from app.schemas.governance import (
    GovernancePolicyIn,
    ModelCreate,
    ProviderCreate,
    ProviderPatch,
    TenantQuotaIn,
    TenantQuotaOut,
)
from app.tasks.queue import async_redis


class GovernanceService:
    def __init__(self, session: AsyncSession, context: TenantContext, request_id: str = "") -> None:
        self.session = session
        self.context = context
        self.request_id = request_id

    async def providers(self) -> list[dict[str, Any]]:
        rows = (
            await self.session.scalars(
                select(AIModelProvider)
                .where(AIModelProvider.tenant_id == self.context.tenant_id)
                .order_by(AIModelProvider.code)
            )
        ).all()
        return [self._provider_out(row) for row in rows]

    async def create_provider(self, payload: ProviderCreate) -> dict[str, Any]:
        row = AIModelProvider(
            tenant_id=self.context.tenant_id,
            code=payload.code,
            display_name=payload.display_name,
            base_url=str(payload.base_url).rstrip("/"),
            secret_env_name=payload.secret_env_name,
            data_region=payload.data_region,
            status="DISABLED",
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(row)
        await self.session.flush()
        self._audit("PROVIDER_CREATED", "model_provider", str(row.id), {"code": row.code})
        await self.session.commit()
        await self.session.refresh(row)
        return self._provider_out(row)

    async def patch_provider(self, provider_id: int, payload: ProviderPatch) -> dict[str, Any]:
        row = await self._provider(provider_id, lock=True)
        values = payload.model_dump(exclude_unset=True)
        if values.get("status") == "ACTIVE":
            if not os.getenv(str(values.get("secret_env_name") or row.secret_env_name), ""):
                raise AppError("部署环境未提供 Provider Secret", code=40970, status_code=409)
            if row.last_probe_status != "HEALTHY":
                raise AppError("Provider 探测成功前不能启用", code=40971, status_code=409)
        for key, value in values.items():
            setattr(row, key, str(value).rstrip("/") if key == "base_url" else value)
        row.updated_by = self.context.user_id
        self._audit("PROVIDER_UPDATED", "model_provider", str(row.id), {"fields": sorted(values)})
        await self.session.commit()
        return self._provider_out(row)

    async def probe_provider(self, provider_id: int) -> dict[str, Any]:
        """使用部署 Secret 做真实兼容性探测；保存配置不等于探测成功。"""
        row = await self._provider(provider_id, lock=True)
        secret = os.getenv(row.secret_env_name, "")
        if not secret:
            raise AppError("部署环境未提供 Provider Secret", code=40970, status_code=409)
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{row.base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {secret}"},
                )
            row.last_probe_status = "HEALTHY" if response.status_code < 400 else f"HTTP_{response.status_code}"
        except httpx.HTTPError:
            row.last_probe_status = "UNREACHABLE"
        row.last_probe_at = datetime.now(UTC)
        self._audit(
            "PROVIDER_PROBED",
            "model_provider",
            str(row.id),
            {"status": row.last_probe_status},
        )
        await self.session.commit()
        return self._provider_out(row)

    async def models(self) -> list[AIModelDefinition]:
        return list(
            (
                await self.session.scalars(
                    select(AIModelDefinition)
                    .where(AIModelDefinition.tenant_id == self.context.tenant_id)
                    .order_by(AIModelDefinition.model_name)
                )
            ).all()
        )

    async def create_model(self, payload: ModelCreate) -> AIModelDefinition:
        provider = await self._provider(payload.provider_id)
        if payload.enabled and provider.status != "ACTIVE":
            raise AppError("Provider 未启用，模型不能启用", code=40972, status_code=409)
        prices = (payload.input_price, payload.output_price, payload.currency, payload.pricing_version)
        if any(value is not None for value in prices) and not all(value is not None for value in prices):
            raise AppError("价格、币种和价格版本必须同时提供", code=42270, status_code=422)
        row = AIModelDefinition(
            tenant_id=self.context.tenant_id,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
            **payload.model_dump(),
        )
        self.session.add(row)
        await self.session.flush()
        self._audit("MODEL_CREATED", "model", str(row.id), {"model": row.model_name})
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def policy(self) -> AIGovernancePolicy | dict[str, Any]:
        row = await self.session.scalar(
            select(AIGovernancePolicy).where(
                AIGovernancePolicy.tenant_id == self.context.tenant_id
            )
        )
        return row or self._policy_defaults()

    async def replace_policy(self, payload: GovernancePolicyIn) -> AIGovernancePolicy:
        row = await self.session.scalar(
            select(AIGovernancePolicy)
            .where(AIGovernancePolicy.tenant_id == self.context.tenant_id)
            .with_for_update()
        )
        if row is None:
            row = AIGovernancePolicy(
                tenant_id=self.context.tenant_id,
                updated_by=self.context.user_id,
                **payload.model_dump(),
            )
            self.session.add(row)
        else:
            for key, value in payload.model_dump().items():
                setattr(row, key, value)
            row.updated_by = self.context.user_id
        self._audit("POLICY_REPLACED", "governance_policy", "tenant", payload.model_dump())
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def quota(self) -> TenantAIQuota | dict[str, Any]:
        row = await self.session.scalar(
            select(TenantAIQuota).where(TenantAIQuota.tenant_id == self.context.tenant_id)
        )
        return row or self._quota_defaults()

    async def replace_quota(self, payload: TenantQuotaIn) -> TenantAIQuota:
        row = await self.session.scalar(
            select(TenantAIQuota)
            .where(TenantAIQuota.tenant_id == self.context.tenant_id)
            .with_for_update()
        )
        if row is None:
            row = TenantAIQuota(
                tenant_id=self.context.tenant_id,
                updated_by=self.context.user_id,
                **payload.model_dump(),
            )
            self.session.add(row)
        else:
            for key, value in payload.model_dump().items():
                setattr(row, key, value)
            row.updated_by = self.context.user_id
        self._audit("QUOTA_REPLACED", "tenant_quota", "tenant", payload.model_dump(mode="json"))
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def usage(self) -> dict[str, Any]:
        month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rows = (
            await self.session.execute(
                select(
                    ModelCall.model_provider,
                    ModelCall.model_name,
                    func.count(),
                    func.sum(ModelCall.input_tokens),
                    func.sum(ModelCall.output_tokens),
                    func.sum(ModelCall.estimated_cost),
                    func.count().filter(ModelCall.input_tokens.is_(None)),
                )
                .where(
                    ModelCall.tenant_id == self.context.tenant_id,
                    ModelCall.started_at >= month,
                )
                .group_by(ModelCall.model_provider, ModelCall.model_name)
            )
        ).all()
        items = []
        for row in rows:
            input_tokens, output_tokens, estimated_cost = row[3], row[4], row[5]
            items.append(
                {
                    "provider": row[0],
                    "model": row[1],
                    "calls": int(row[2]),
                    "input_tokens": int(input_tokens) if input_tokens is not None else None,
                    "output_tokens": int(output_tokens) if output_tokens is not None else None,
                    "estimated_cost": float(estimated_cost) if estimated_cost is not None else None,
                    "unknown_usage_calls": int(row[6]),
                }
            )
        return {
            "period_start": month.isoformat(),
            "items": items,
            "quota": TenantQuotaOut.model_validate(await self.quota()).model_dump(mode="json"),
        }

    async def operations(self) -> dict[str, Any]:
        model_calls_total = await self._count(ModelCall)
        model_calls_succeeded = await self._count(ModelCall, ModelCall.status == "SUCCEEDED")
        output: dict[str, Any] = {
            "model_calls_total": float(model_calls_total),
            "model_calls_succeeded": float(model_calls_succeeded),
            "model_failures": float(await self._count(ModelCall, ModelCall.status == "FAILED")),
            "model_429": float(
                await self._count(ModelCall, ModelCall.error_code.between(42900, 42999))
            ),
            "model_5xx": float(
                await self._count(ModelCall, ModelCall.error_code.between(50200, 50299))
            ),
            "model_p50_ms": await self._percentile(ModelCall, ModelCall.duration_ms, 0.5),
            "model_p95_ms": await self._percentile(ModelCall, ModelCall.duration_ms, 0.95),
            "tool_p50_ms": await self._percentile(ToolRun, ToolRun.duration_ms, 0.5),
            "tool_p95_ms": await self._percentile(ToolRun, ToolRun.duration_ms, 0.95),
            "agent_p50_ms": await self._percentile(AgentRun, AgentRun.total_duration_ms, 0.5),
            "agent_p95_ms": await self._percentile(AgentRun, AgentRun.total_duration_ms, 0.95),
            "unknown_executions": float(
                await self._count(ActionExecution, ActionExecution.status == "UNKNOWN")
            ),
            "active_workflows": float(
                await self._count(
                    WorkflowInstance,
                    WorkflowInstance.status.in_(("QUEUED", "RUNNING", "RECONCILING")),
                )
            ),
            "active_evaluations": float(
                await self._count(
                    AgentEvaluationRun, AgentEvaluationRun.status.in_(("QUEUED", "RUNNING"))
                )
            ),
            "active_insights": float(
                await self._count(
                    InsightDetectionRun, InsightDetectionRun.status.in_(("QUEUED", "RUNNING"))
                )
            ),
            "expired_leases": float(
                await self._count(
                    WorkflowInstance,
                    WorkflowInstance.lease_until < func.now(),
                    WorkflowInstance.status.in_(("RUNNING", "RECONCILING")),
                )
            ),
        }
        output["model_success_rate"] = (
            round(model_calls_succeeded / model_calls_total, 4) if model_calls_total else None
        )
        try:
            redis = async_redis()
            output["redis_status"] = "UP" if await redis.ping() else "UNKNOWN"
            output["workflow_queue_depth"] = int(await redis.llen(settings.workflow_queue_key))
            output["evaluation_queue_depth"] = int(await redis.llen(settings.evaluation_queue_key))
            output["insight_queue_depth"] = int(await redis.llen(settings.insight_queue_key))
        except RedisError:
            output.update(
                {
                    "redis_status": "DOWN",
                    "workflow_queue_depth": None,
                    "evaluation_queue_depth": None,
                    "insight_queue_depth": None,
                }
            )
        return output

    async def audits(self, limit: int = 100) -> list[AIGovernanceAudit]:
        return list(
            (
                await self.session.scalars(
                    select(AIGovernanceAudit)
                    .where(AIGovernanceAudit.tenant_id == self.context.tenant_id)
                    .order_by(AIGovernanceAudit.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def retention_preview(self, dry_run: bool) -> AIRetentionRun:
        if not dry_run:
            raise AppError("物理清理需要独立审批流程，V11 API 仅开放 Dry Run", code=40375, status_code=403)
        policy = await self.policy()
        trace_days = int(self._value(policy, "trace_retention_days"))
        conversation_days = int(self._value(policy, "conversation_retention_days"))
        trace_cutoff = datetime.now(UTC) - timedelta(days=trace_days)
        conversation_cutoff = datetime.now(UTC) - timedelta(days=conversation_days)
        counts = {
            "model_calls": await self._count(ModelCall, ModelCall.started_at < trace_cutoff),
            "agent_runs": await self._count(AgentRun, AgentRun.started_at < trace_cutoff),
            "conversations": await self._count(
                Conversation, Conversation.updated_at < conversation_cutoff
            ),
        }
        row = AIRetentionRun(
            tenant_id=self.context.tenant_id,
            requested_by=self.context.user_id,
            dry_run=True,
            status="SUCCEEDED",
            cutoff_summary={
                "trace_before": trace_cutoff.isoformat(),
                "conversation_before": conversation_cutoff.isoformat(),
            },
            affected_summary=counts,
            finished_at=datetime.now(UTC),
        )
        self.session.add(row)
        self._audit("RETENTION_DRY_RUN", "retention", "tenant", counts)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def _provider(self, provider_id: int, lock: bool = False) -> AIModelProvider:
        stmt = select(AIModelProvider).where(
            AIModelProvider.tenant_id == self.context.tenant_id,
            AIModelProvider.id == provider_id,
        )
        row = await self.session.scalar(stmt.with_for_update() if lock else stmt)
        if row is None:
            raise AppError("模型 Provider 不存在", code=40470, status_code=404)
        return row

    @staticmethod
    def _provider_out(row: AIModelProvider) -> dict[str, Any]:
        return {
            "id": row.id,
            "code": row.code,
            "display_name": row.display_name,
            "base_url": row.base_url,
            "secret_env_name": row.secret_env_name,
            "secret_configured": bool(os.getenv(row.secret_env_name, "")),
            "status": row.status,
            "data_region": row.data_region,
            "last_probe_status": row.last_probe_status,
            "last_probe_at": row.last_probe_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _audit(self, action: str, target_type: str, target_id: str, detail: dict) -> None:
        self.session.add(
            AIGovernanceAudit(
                tenant_id=self.context.tenant_id,
                actor_user_id=self.context.user_id or None,
                actor_type=self.context.subject_type,
                action=action,
                target_type=target_type,
                target_id=target_id,
                outcome="SUCCEEDED",
                safe_detail=detail,
                request_id=self.request_id,
            )
        )

    def _policy_defaults(self) -> dict[str, Any]:
        return {
            "id": 0,
            **GovernancePolicyIn().model_dump(),
            "updated_by": 0,
            "updated_at": datetime.now(UTC),
        }

    def _quota_defaults(self) -> dict[str, Any]:
        return {
            "id": 0,
            **TenantQuotaIn().model_dump(),
            "updated_by": 0,
            "updated_at": datetime.now(UTC),
        }

    async def _count(self, model: Any, *filters: Any) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.tenant_id == self.context.tenant_id, *filters)
        )
        return int(value or 0)

    async def _percentile(self, model: Any, column: Any, quantile: float) -> float | None:
        value = await self.session.scalar(
            select(func.percentile_cont(quantile).within_group(column)).where(
                model.tenant_id == self.context.tenant_id,
                column.is_not(None),
            )
        )
        return float(value) if value is not None else None

    @staticmethod
    def _value(row: Any, name: str) -> Any:
        return row[name] if isinstance(row, dict) else getattr(row, name)
