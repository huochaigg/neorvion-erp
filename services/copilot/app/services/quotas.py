from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.evaluation import ModelPricing
from app.models.governance import (
    AIBudgetReservation,
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
        return RuntimeGovernance(
            None, True, settings.tool_max_calls, int(settings.tool_total_timeout_seconds)
        )
    policy = await session.scalar(
        select(AIGovernancePolicy).where(AIGovernancePolicy.tenant_id == tenant_id)
    )
    if policy is not None:
        if (
            policy.allowed_provider_codes
            and settings.model_provider not in policy.allowed_provider_codes
        ):
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
local money_reserved=tonumber(redis.call('GET',KEYS[6]) or '0')
local money_used=tonumber(redis.call('GET',KEYS[7]) or '0')
if redis.call('EXISTS',KEYS[8]) == 1 then return {0,5} end
if rpm >= tonumber(ARGV[1]) then return {0,1} end
if day >= tonumber(ARGV[2]) then return {0,2} end
if used + reserved + tonumber(ARGV[3]) > tonumber(ARGV[4]) then return {0,3} end
if concurrent >= tonumber(ARGV[5]) then return {0,4} end
if tonumber(ARGV[8]) >= 0 and money_used + money_reserved + tonumber(ARGV[7]) > tonumber(ARGV[8]) then return {0,6} end
redis.call('INCR',KEYS[1]); redis.call('EXPIRE',KEYS[1],120)
redis.call('INCR',KEYS[2]); redis.call('EXPIRE',KEYS[2],172800)
redis.call('INCRBY',KEYS[3],ARGV[3]); redis.call('EXPIRE',KEYS[3],2678400)
redis.call('INCR',KEYS[5]); redis.call('EXPIRE',KEYS[5],tonumber(ARGV[6]))
redis.call('INCRBY',KEYS[6],ARGV[7]); redis.call('EXPIRE',KEYS[6],2678400)
redis.call('HSET',KEYS[8],'status','ACTIVE','tokens',ARGV[3],'money_micros',ARGV[7],'pricing_version',ARGV[9],'scenario',ARGV[10])
redis.call('EXPIRE',KEYS[8],2678400)
return {1,used,reserved+tonumber(ARGV[3]),concurrent+1,money_used,money_reserved+tonumber(ARGV[7])}
"""

_SETTLE_SCRIPT = """
if redis.call('HGET',KEYS[1],'status') ~= 'ACTIVE' then return 0 end
local token_reserved=tonumber(redis.call('HGET',KEYS[1],'tokens') or '0')
local money_reserved=tonumber(redis.call('HGET',KEYS[1],'money_micros') or '0')
local token_charge=tonumber(ARGV[1]) >= 0 and math.min(token_reserved,tonumber(ARGV[1])) or token_reserved
local money_charge=tonumber(ARGV[2]) >= 0 and math.min(money_reserved,tonumber(ARGV[2])) or money_reserved
redis.call('DECRBY',KEYS[2],math.min(tonumber(redis.call('GET',KEYS[2]) or '0'),token_reserved))
redis.call('INCRBY',KEYS[3],token_charge); redis.call('EXPIRE',KEYS[3],2678400)
local concurrent=tonumber(redis.call('GET',KEYS[4]) or '0')
if concurrent > 0 then redis.call('DECR',KEYS[4]) end
redis.call('DECRBY',KEYS[5],math.min(tonumber(redis.call('GET',KEYS[5]) or '0'),money_reserved))
redis.call('INCRBY',KEYS[6],money_charge); redis.call('EXPIRE',KEYS[6],2678400)
redis.call('INCRBY',KEYS[7],token_charge); redis.call('EXPIRE',KEYS[7],2678400)
redis.call('INCRBY',KEYS[8],money_charge); redis.call('EXPIRE',KEYS[8],2678400)
redis.call('HSET',KEYS[1],'status','SETTLED','charged_tokens',token_charge,'charged_money_micros',money_charge)
return 1
"""

_ABORT_SCRIPT = """
if redis.call('HGET',KEYS[1],'status') ~= 'ACTIVE' then return 0 end
local tokens=tonumber(redis.call('HGET',KEYS[1],'tokens') or '0')
local money=tonumber(redis.call('HGET',KEYS[1],'money_micros') or '0')
redis.call('DECRBY',KEYS[2],math.min(tonumber(redis.call('GET',KEYS[2]) or '0'),tokens))
local concurrent=tonumber(redis.call('GET',KEYS[3]) or '0')
if concurrent > 0 then redis.call('DECR',KEYS[3]) end
redis.call('DECRBY',KEYS[4],math.min(tonumber(redis.call('GET',KEYS[4]) or '0'),money))
redis.call('HSET',KEYS[1],'status','ABORTED')
return 1
"""


@dataclass(slots=True)
class QuotaReservation:
    tenant_id: int
    estimated_tokens: int
    estimated_money_micros: int
    month_key: str
    reservation_id: str
    scenario: str
    max_price_per_token_micros: Decimal
    session: AsyncSession
    audit_row: AIBudgetReservation
    active: bool = True

    async def settle(self, actual_tokens: int | None, *, usage_trusted: bool = False) -> None:
        """幂等结算预留；Usage 不可信或缺失时按事前保守上限扣减。"""
        if not self.active:
            return
        prefix = f"copilot:quota:{self.tenant_id}:{self.month_key}"
        charged_tokens = actual_tokens if usage_trusted and actual_tokens is not None else -1
        charged_money = (
            _ceil_decimal(Decimal(actual_tokens) * self.max_price_per_token_micros)
            if usage_trusted and actual_tokens is not None
            else -1
        )
        settled = await async_redis().eval(
            _SETTLE_SCRIPT,
            8,
            f"{prefix}:reservation:{self.reservation_id}",
            f"{prefix}:reserved",
            f"{prefix}:used",
            f"copilot:quota:{self.tenant_id}:concurrent",
            f"{prefix}:money:reserved",
            f"{prefix}:money:used",
            f"{prefix}:scenario:{self.scenario}:used",
            f"{prefix}:scenario:{self.scenario}:money:used",
            charged_tokens,
            charged_money,
        )
        if settled:
            self.audit_row.status = "SETTLED"
            self.audit_row.charged_tokens = (
                min(self.estimated_tokens, charged_tokens)
                if charged_tokens >= 0
                else self.estimated_tokens
            )
            self.audit_row.charged_money_micros = (
                min(self.estimated_money_micros, charged_money)
                if charged_money >= 0
                else self.estimated_money_micros
            )
            self.audit_row.usage_trusted = usage_trusted and actual_tokens is not None
            self.audit_row.settled_at = datetime.now(UTC)
            try:
                await self.session.commit()
            except Exception as exc:
                await self.session.rollback()
                raise AppError("预算结算审计写入失败", code=50378, status_code=503) from exc
        self.active = False

    async def cancel(self) -> None:
        await self.settle(None)


class NoopReservation:
    async def settle(self, actual_tokens: int | None, *, usage_trusted: bool = False) -> None:
        del actual_tokens, usage_trusted

    async def cancel(self) -> None:
        return None


async def reserve_chat_quota(
    session: AsyncSession,
    tenant_id: int,
    estimated_tokens: int,
    *,
    scenario: str = "CHAT",
) -> QuotaReservation | NoopReservation:
    """Redis Lua 原子预留请求、Token、金额和并发额度。

    聊天存在多 Agent 和多轮模型调用，因此使用受配置上限约束的保守
    调用次数计算最大费用；价格、币种或版本不可确定时失败关闭。
    """
    if not settings.quota_enforcement_enabled:
        return NoopReservation()
    quota = await session.scalar(select(TenantAIQuota).where(TenantAIQuota.tenant_id == tenant_id))
    rpm = quota.requests_per_minute if quota else 30
    day_limit = quota.requests_per_day if quota else 1000
    monthly = quota.monthly_token_limit if quota else 1_000_000
    concurrency = quota.max_concurrent_agents if quota else 3
    if settings.is_production and (quota is None or quota.monthly_budget is None):
        raise AppError("生产租户未配置金额预算", code=50377, status_code=503)
    pricing = await _active_pricing(session, tenant_id)
    money_limit_micros = -1
    estimated_money_micros = 0
    max_price_per_token_micros = Decimal(0)
    pricing_version = "NOT_CONFIGURED"
    if quota is not None and quota.monthly_budget is not None:
        if pricing is None or pricing.currency.upper() != quota.currency.upper():
            raise AppError("模型价格或币种未正确配置", code=50377, status_code=503)
        max_price_per_token_micros = (
            max(Decimal(str(pricing.input_price)), Decimal(str(pricing.output_price)))
            * Decimal(1_000_000)
            / Decimal(pricing.unit_tokens)
        )
        bounded_calls = max(1, settings.budget_max_model_calls_per_request)
        estimated_money_micros = _ceil_decimal(
            Decimal(max(1, estimated_tokens) * bounded_calls) * max_price_per_token_micros
        )
        money_limit_micros = _ceil_decimal(Decimal(quota.monthly_budget) * Decimal(1_000_000))
        pricing_version = pricing.pricing_version
    now = datetime.now(UTC)
    minute = now.strftime("%Y%m%d%H%M")
    day = now.strftime("%Y%m%d")
    month = now.strftime("%Y%m")
    prefix = f"copilot:quota:{tenant_id}"
    reservation_id = uuid4().hex
    audit_row = AIBudgetReservation(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        scenario=scenario.upper(),
        period_key=month,
        status="PENDING",
        estimated_tokens=max(1, estimated_tokens),
        estimated_money_micros=estimated_money_micros,
        currency=quota.currency if quota is not None else "N/A",
        pricing_version=pricing_version,
    )
    session.add(audit_row)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise AppError("预算预留审计不可用", code=50378, status_code=503) from exc
    try:
        result = await async_redis().eval(
            _RESERVE_SCRIPT,
            8,
            f"{prefix}:rpm:{minute}",
            f"{prefix}:day:{day}",
            f"{prefix}:{month}:reserved",
            f"{prefix}:{month}:used",
            f"{prefix}:concurrent",
            f"{prefix}:{month}:money:reserved",
            f"{prefix}:{month}:money:used",
            f"{prefix}:{month}:reservation:{reservation_id}",
            rpm,
            day_limit,
            max(1, estimated_tokens),
            monthly,
            concurrency,
            int(max(60, settings.tool_total_timeout_seconds * 2)),
            estimated_money_micros,
            money_limit_micros,
            pricing_version,
            scenario.upper(),
        )
    except Exception as exc:
        audit_row.status = "FAILED"
        await session.commit()
        raise AppError("AI 配额服务暂时不可用", code=50376, status_code=503) from exc
    if not result or int(result[0]) != 1:
        reason = int(result[1]) if result and len(result) > 1 else 0
        messages = {
            1: "分钟请求配额已用尽",
            2: "每日请求配额已用尽",
            3: "月度 Token 配额不足",
            4: "并发 Agent 配额已用尽",
            5: "预算预留标识冲突",
            6: "月度金额预算不足",
        }
        audit_row.status = "REJECTED"
        await session.commit()
        raise AppError(messages.get(reason, "AI 配额已用尽"), code=42976, status_code=429)
    audit_row.status = "ACTIVE"
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        await async_redis().eval(
            _ABORT_SCRIPT,
            4,
            f"{prefix}:{month}:reservation:{reservation_id}",
            f"{prefix}:{month}:reserved",
            f"{prefix}:concurrent",
            f"{prefix}:{month}:money:reserved",
        )
        raise AppError("预算预留审计不可用", code=50378, status_code=503) from exc
    return QuotaReservation(
        tenant_id,
        max(1, estimated_tokens),
        estimated_money_micros,
        month,
        reservation_id,
        scenario.upper(),
        max_price_per_token_micros,
        session,
        audit_row,
    )


async def _active_pricing(session: AsyncSession, tenant_id: int) -> ModelPricing | None:
    now = datetime.now(UTC)
    return await session.scalar(
        select(ModelPricing)
        .where(
            ModelPricing.tenant_id == tenant_id,
            ModelPricing.provider == settings.model_provider,
            ModelPricing.model == settings.chat_model,
            ModelPricing.enabled.is_(True),
            ModelPricing.effective_from <= now,
        )
        .order_by(ModelPricing.effective_from.desc())
        .limit(1)
    )


def _ceil_decimal(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_CEILING))


def usage_tokens(usage: object) -> int | None:
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    if prompt is None or completion is None:
        return None
    return int(prompt) + int(completion)
