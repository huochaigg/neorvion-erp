from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.governance import (
    AIGovernancePolicy,
    AIModelDefinition,
    AIModelProvider,
    TenantAIQuota,
)
from app.tasks.queue import async_redis


@dataclass(frozen=True, slots=True)
class RuntimeGovernance:
    allowed_tools: frozenset[str] | None
    allow_multi_agent: bool
    max_tool_calls: int
    max_execution_seconds: int


async def enforce_runtime_governance(
    session: AsyncSession, tenant_id: int, purpose: str
) -> RuntimeGovernance:
    """在模型入口执行租户策略与模型目录交集；空目录保持已有部署配置。"""
    if settings.app_env.lower() in {"test", "testing"}:
        return RuntimeGovernance(None, True, settings.tool_max_calls, int(settings.tool_total_timeout_seconds))
    policy = await session.scalar(
        select(AIGovernancePolicy).where(AIGovernancePolicy.tenant_id == tenant_id)
    )
    if policy is not None:
        if policy.allowed_provider_codes and settings.model_provider not in policy.allowed_provider_codes:
            raise AppError("当前模型 Provider 不符合租户策略", code=40377, status_code=403)
        if policy.allowed_model_names and settings.chat_model not in policy.allowed_model_names:
            raise AppError("当前模型不符合租户策略", code=40377, status_code=403)
    configured = list(
        (
            await session.scalars(
                select(AIModelDefinition)
                .join(
                    AIModelProvider,
                    (AIModelProvider.id == AIModelDefinition.provider_id)
                    & (AIModelProvider.tenant_id == AIModelDefinition.tenant_id),
                )
                .where(AIModelDefinition.tenant_id == tenant_id)
            )
        ).all()
    )
    if configured and not any(
        row.enabled and row.model_name == settings.chat_model and purpose in set(row.purposes or [])
        for row in configured
    ):
        raise AppError("当前用途没有启用的模型", code=40377, status_code=403)
    quota = await session.scalar(select(TenantAIQuota).where(TenantAIQuota.tenant_id == tenant_id))
    return RuntimeGovernance(
        allowed_tools=(
            frozenset(policy.allowed_tools) if policy is not None and policy.allowed_tools else None
        ),
        allow_multi_agent=bool(policy.multi_agent_enabled) if policy is not None else True,
        max_tool_calls=quota.max_tool_calls_per_request if quota else settings.tool_max_calls,
        max_execution_seconds=quota.max_execution_seconds
        if quota
        else int(settings.tool_total_timeout_seconds),
    )

_RESERVE_SCRIPT = """
local rpm=tonumber(redis.call('GET',KEYS[1]) or '0')
local day=tonumber(redis.call('GET',KEYS[2]) or '0')
local reserved=tonumber(redis.call('GET',KEYS[3]) or '0')
local used=tonumber(redis.call('GET',KEYS[4]) or '0')
local concurrent=tonumber(redis.call('GET',KEYS[5]) or '0')
if rpm >= tonumber(ARGV[1]) then return {0,1} end
if day >= tonumber(ARGV[2]) then return {0,2} end
if used + reserved + tonumber(ARGV[3]) > tonumber(ARGV[4]) then return {0,3} end
if concurrent >= tonumber(ARGV[5]) then return {0,4} end
redis.call('INCR',KEYS[1]); redis.call('EXPIRE',KEYS[1],120)
redis.call('INCR',KEYS[2]); redis.call('EXPIRE',KEYS[2],172800)
redis.call('INCRBY',KEYS[3],ARGV[3]); redis.call('EXPIRE',KEYS[3],2678400)
redis.call('INCR',KEYS[5]); redis.call('EXPIRE',KEYS[5],tonumber(ARGV[6]))
return {1,used,reserved+tonumber(ARGV[3]),concurrent+1}
"""

_SETTLE_SCRIPT = """
local reserved=tonumber(redis.call('GET',KEYS[1]) or '0')
local release=math.min(reserved,tonumber(ARGV[1]))
redis.call('DECRBY',KEYS[1],release)
local concurrent=tonumber(redis.call('GET',KEYS[3]) or '0')
if concurrent > 0 then redis.call('DECR',KEYS[3]) end
if tonumber(ARGV[2]) >= 0 then
  redis.call('INCRBY',KEYS[2],ARGV[2]); redis.call('EXPIRE',KEYS[2],2678400)
end
return 1
"""


@dataclass(slots=True)
class QuotaReservation:
    tenant_id: int
    estimated_tokens: int
    month_key: str
    active: bool = True

    async def settle(self, actual_tokens: int | None) -> None:
        if not self.active:
            return
        prefix = f"copilot:quota:{self.tenant_id}:{self.month_key}"
        await async_redis().eval(
            _SETTLE_SCRIPT,
            3,
            f"{prefix}:reserved",
            f"{prefix}:used",
            f"copilot:quota:{self.tenant_id}:concurrent",
            self.estimated_tokens,
            actual_tokens if actual_tokens is not None else -1,
        )
        self.active = False

    async def cancel(self) -> None:
        await self.settle(None)


class NoopReservation:
    async def settle(self, actual_tokens: int | None) -> None:
        del actual_tokens

    async def cancel(self) -> None:
        return None


async def reserve_chat_quota(
    session: AsyncSession, tenant_id: int, estimated_tokens: int
) -> QuotaReservation | NoopReservation:
    """Redis Lua 原子预留请求、Token 和并发额度，失败时不允许模型调用。"""
    if not settings.quota_enforcement_enabled:
        return NoopReservation()
    quota = await session.scalar(select(TenantAIQuota).where(TenantAIQuota.tenant_id == tenant_id))
    rpm = quota.requests_per_minute if quota else 30
    day_limit = quota.requests_per_day if quota else 1000
    monthly = quota.monthly_token_limit if quota else 1_000_000
    concurrency = quota.max_concurrent_agents if quota else 3
    now = datetime.now(UTC)
    minute = now.strftime("%Y%m%d%H%M")
    day = now.strftime("%Y%m%d")
    month = now.strftime("%Y%m")
    prefix = f"copilot:quota:{tenant_id}"
    try:
        result = await async_redis().eval(
            _RESERVE_SCRIPT,
            5,
            f"{prefix}:rpm:{minute}",
            f"{prefix}:day:{day}",
            f"{prefix}:{month}:reserved",
            f"{prefix}:{month}:used",
            f"{prefix}:concurrent",
            rpm,
            day_limit,
            max(1, estimated_tokens),
            monthly,
            concurrency,
            int(max(60, settings.tool_total_timeout_seconds * 2)),
        )
    except Exception as exc:
        raise AppError("AI 配额服务暂时不可用", code=50376, status_code=503) from exc
    if not result or int(result[0]) != 1:
        reason = int(result[1]) if result and len(result) > 1 else 0
        messages = {
            1: "分钟请求配额已用尽",
            2: "每日请求配额已用尽",
            3: "月度 Token 配额不足",
            4: "并发 Agent 配额已用尽",
        }
        raise AppError(messages.get(reason, "AI 配额已用尽"), code=42976, status_code=429)
    return QuotaReservation(tenant_id, max(1, estimated_tokens), month)


def usage_tokens(usage: object) -> int | None:
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    if prompt is None or completion is None:
        return None
    return int(prompt) + int(completion)
