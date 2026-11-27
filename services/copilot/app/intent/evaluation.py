"""意图评测执行器。规则回放与 Live 分类分开，不把 Mock 成功写成生产验收。"""

from __future__ import annotations

import time
from typing import Any

from app.ai.types import ChatAdapter
from app.core.tenant import TenantContext
from app.intent.context import ContextResolver
from app.intent.flags import intent_mode
from app.intent.service import IntentUnderstandingService


async def run_intent_case(
    case: dict[str, Any],
    *,
    adapter: ChatAdapter | None = None,
    tenant_id: int = 0,
    user_id: int = 0,
) -> dict[str, Any]:
    """
    输入：冻结 Case（含人工 expected 与可选上下文）。
    输出：结构化实际结果，供现有 evaluate_case 打分。
    边界：不调用 ERP 写接口，不创建 Proposal。
    """
    scenario = case.get("scenario_config") or {}
    context_value = scenario.get("context") if isinstance(scenario, dict) else None
    raw_context: dict[str, Any] = context_value if isinstance(context_value, dict) else {}
    messages = list(raw_context.get("messages") or [])
    started = time.perf_counter()
    context = ContextResolver().resolve(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=None,
        current_text=str(case.get("user_input") or ""),
        recent_messages=messages,
    )
    resolution = await IntentUnderstandingService().resolve(
        context,
        adapter=adapter,
        force_mode="ENABLED",
    )
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    blocked = (
        adapter is not None
        and resolution.classifier_method in {"FALLBACK"}
        and resolution.fallback_reason
        in {"classifier_unavailable", "classifier_timeout", "classifier_error", "invalid_json"}
    )
    return {
        "transport_success": True,
        "agent_completed": True,
        "blocked": blocked,
        "resolved_intents": list(resolution.resolved_intents),
        "problem_types": list(resolution.problem_types),
        "decision": resolution.decision,
        "query_shapes": [task.query_shape for task in resolution.tasks if task.query_shape],
        "clarification": bool(resolution.clarification),
        "missing_slots": list(resolution.missing_slots),
        "selected_skill_keys": list(resolution.routing_plan.skill_keys),
        "selection_method": resolution.routing_plan.skill_policy,
        "mode": resolution.routing_plan.agent_mode,
        "allow_propose_action": resolution.tool_policy.allow_propose_action,
        "unsafe_action_attempts": 0 if not resolution.tool_policy.allow_propose_action else 0,
        "unsafe_action_executions": 0,
        "tool_calls": [],
        "evidences": [],
        "latency_ms": elapsed,
        "selector_latency_ms": resolution.latency_ms,
        "model_calls": 1 if resolution.llm_called else 0,
        "embedding_calls": 0,
        "usage": (
            {
                "input_tokens": (resolution.model_usage or {}).get("prompt_tokens"),
                "output_tokens": (resolution.model_usage or {}).get("completion_tokens"),
            }
            if resolution.model_usage
            else None
        ),
        "feature_mode": intent_mode(),
        "intent_trace": resolution.diagnostic_payload(),
        "answer": resolution.clarification or resolution.public_status,
    }


def evaluation_tenant(run_tenant_id: int, run_user_id: int, permissions: frozenset[str]) -> TenantContext:
    return TenantContext(
        user_id=run_user_id,
        tenant_id=run_tenant_id,
        member_id=0,
        is_owner=False,
        role="EVALUATION",
        role_codes=("EVALUATION",),
        permission_codes=permissions,
        token_jti=f"evaluation-intent-{run_tenant_id}",
        token_version=0,
        authz_version=0,
    )
