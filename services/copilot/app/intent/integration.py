"""把意图理解结果接到现有 Chat / Agent / Skill / Tool 运行时，避免第二套执行体系。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ChatAdapter
from app.core.tenant import TenantContext
from app.graph.workflow import AgentRuntime
from app.intent.context import ContextResolver
from app.intent.flags import intent_active, intent_applied
from app.intent.schemas import IntentResolution
from app.intent.service import IntentUnderstandingService
from app.intent.store import IntentContextStore


@dataclass(frozen=True, slots=True)
class IntentClarification:
    """与 PendingSkillPrompt 同形，Chat API 可复用 complete_without_run。"""

    answer: str
    public_data: dict[str, Any]


async def resolve_chat_intent(
    *,
    db: AsyncSession | None,
    context: TenantContext,
    text: str,
    request_id: str,
    conversation_id: int | None,
    message_id: int | None = None,
    recent_messages: list[dict[str, str]] | None = None,
    adapter: ChatAdapter | None = None,
    skill_mode: str = "AUTO",
    explicit_skill_key: str | None = None,
    pending_skill_key: str | None = None,
    has_open_proposal: bool = False,
) -> IntentResolution:
    """Chat 入口的唯一 Feature Flag 判断点。业务代码消费 resolution，不再散落开关。"""
    service = IntentUnderstandingService()
    if not intent_active():
        return await service.resolve(ContextResolver().resolve(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            conversation_id=conversation_id,
            current_text=text,
        ))
    store = IntentContextStore(db, context) if db is not None and conversation_id is not None else None
    row = await store.load(conversation_id) if store is not None and conversation_id is not None else None
    cancel_requested = _is_cancel(text) or skill_mode == "NONE"
    if cancel_requested and store is not None and conversation_id is not None:
        await store.cancel(conversation_id, request_id)
    resolved_context = ContextResolver().resolve(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        conversation_id=conversation_id,
        current_text=text,
        recent_messages=recent_messages,
        stored_entities=list(row.entities) if row is not None else None,
        pending=store.pending_payload(row) if store is not None else {},
        pending_skill_key=pending_skill_key,
        has_open_proposal=has_open_proposal,
    )
    resolution = await service.resolve(
        resolved_context,
        adapter=adapter,
        skill_mode=skill_mode,
        explicit_skill_key=explicit_skill_key,
        cancel_requested=cancel_requested,
    )
    if store is not None and conversation_id is not None and intent_applied():
        await store.save_resolution(
            conversation_id,
            resolution,
            request_id=request_id,
            message_id=message_id,
            persist_pending=True,
        )
    return resolution


def apply_resolution_to_runtime(runtime: AgentRuntime, resolution: IntentResolution) -> None:
    """把路由建议写入运行时；SHADOW 只挂结果，不改白名单。"""
    runtime.intent_resolution = resolution
    if not resolution.applied:
        return
    from app.agents.router import AgentRoute

    runtime.intent_route = AgentRoute(
        resolution.routing_plan.agent_mode,
        resolution.routing_plan.agents,
        resolution.routing_plan.reason,
    )
    if not resolution.routing_plan.allow_multi_agent:
        runtime.allow_multi_agent = False
    elif resolution.routing_plan.agent_mode == "multi":
        runtime.allow_multi_agent = True
    if runtime.tools is None:
        return
    runtime.tools.forbid_write_tools = not resolution.tool_policy.allow_propose_action
    runtime.tools.blocked_tools = frozenset(resolution.tool_policy.blocked_tools)


def should_clarify_without_run(resolution: IntentResolution) -> bool:
    return bool(
        resolution.applied
        and resolution.clarification
        and resolution.routing_plan.clarify
        and resolution.decision in {"AMBIGUOUS", "INSUFFICIENT"}
    )


def clarification_response(resolution: IntentResolution) -> IntentClarification:
    answer = resolution.clarification or "请补充更多信息后再继续。"
    return IntentClarification(
        answer=answer,
        public_data=resolution.public_payload() | {"status": "COLLECTING" if resolution.pending else "CLARIFY"},
    )


def _is_cancel(text: str) -> bool:
    stripped = text.strip()
    return stripped in {"取消", "算了", "不用了", "停止"} or stripped.startswith("取消本次")
