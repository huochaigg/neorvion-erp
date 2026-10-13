"""使用统计。全部来自 retrieval_logs 与 messages，禁止硬编码。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.rag import Message, RetrievalLog
from app.schemas.evaluation import UsageStatsOut
from app.services.authorization import AuthorizationService
from app.services.evaluation_run import _estimate_cost, _percentile


class UsageStatsService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()

    async def overview(self, days: int = 7) -> UsageStatsOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 90)))
        tenant_id = self.context.tenant_id
        logs = list(
            (
                await self.session.scalars(
                    select(RetrievalLog).where(
                        RetrievalLog.tenant_id == tenant_id,
                        RetrievalLog.created_at >= since,
                    )
                )
            ).all()
        )
        latencies = [row.latency_ms for row in logs]
        empty = 0
        for row in logs:
            stages = row.stages or {}
            ranks = (stages.get("vector_ranks") or []) + (stages.get("keyword_ranks") or [])
            if not ranks:
                empty += 1
        strategy_counts: dict[str, int] = {}
        for row in logs:
            strategy_counts[row.strategy] = strategy_counts.get(row.strategy, 0) + 1
        messages = list(
            (
                await self.session.scalars(
                    select(Message).where(
                        Message.tenant_id == tenant_id,
                        Message.created_at >= since,
                        Message.role == "ASSISTANT",
                    )
                )
            ).all()
        )
        prompt_tokens = 0
        completion_tokens = 0
        for row in messages:
            usage = row.usage or {}
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)
        return UsageStatsOut(
            query_count=len(logs),
            search_success=len(logs) - empty,
            search_empty=empty,
            latency_p50_ms=_percentile(latencies, 50),
            latency_p95_ms=_percentile(latencies, 95),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=_estimate_cost(prompt_tokens, completion_tokens),
            strategy_counts=strategy_counts,
            note=(
                "费用按环境变量 EVAL_PROMPT_TOKEN_USD / EVAL_COMPLETION_TOKEN_USD 估算；"
                "未配置单价时不返回估算值。"
                if settings.eval_prompt_token_usd <= 0 and settings.eval_completion_token_usd <= 0
                else "费用为按 Token 单价的估算，不是账单。"
            ),
        )
