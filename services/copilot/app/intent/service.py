"""意图理解服务：理解层入口。不执行业务，不授予权限。"""

from __future__ import annotations

import time
from uuid import uuid4

from app.ai.types import ChatAdapter
from app.intent.classifiers.hybrid import HybridIntentClassifier
from app.intent.context import ContextResolver
from app.intent.decision import DecisionEngine
from app.intent.flags import intent_applied, intent_mode
from app.intent.planner import MultiIntentTaskPlanner
from app.intent.policy import ToolAvailabilityPolicy
from app.intent.registry import IntentRegistry, get_intent_registry
from app.intent.routing import RoutingPlanner
from app.intent.schemas import ConversationContext, IntentResolution, RoutingPlan, ToolPolicy


class IntentUnderstandingService:
    """
    输入：当前用户消息、会话上下文、可选模型适配器。
    输出：IntentResolution。
    流程：上下文 → 混合分类 → 裁决 → 多任务规划 → 路由/工具策略。
    边界：DISABLED 立即返回；SHADOW 计算结果但不 applied；失败时写操作 fail-closed。
    """

    def __init__(self, registry: IntentRegistry | None = None) -> None:
        self.registry = registry or get_intent_registry()
        self.resolver = ContextResolver()
        self.classifier = HybridIntentClassifier(self.registry)
        self.decision = DecisionEngine(self.registry)
        self.planner = MultiIntentTaskPlanner()
        self.router = RoutingPlanner()
        self.policy = ToolAvailabilityPolicy()

    async def resolve(
        self,
        context: ConversationContext,
        *,
        adapter: ChatAdapter | None = None,
        skill_mode: str = "AUTO",
        explicit_skill_key: str | None = None,
        cancel_requested: bool = False,
        force_mode: str | None = None,
    ) -> IntentResolution:
        started = time.perf_counter()
        mode = (force_mode or intent_mode()).upper()
        if mode not in {"DISABLED", "SHADOW", "ENABLED"}:
            mode = "DISABLED"
        if mode == "DISABLED":
            return self._disabled(started)
        if cancel_requested:
            return self._cancelled(started)
        classification = await self.classifier.classify(
            context,
            adapter=adapter,
            allow_llm=bool(adapter) if force_mode == "ENABLED" else None,
        )
        decision, tasks, reason = self.decision.decide(classification, context)
        tasks = self.planner.plan(tasks)
        routing = self.router.plan(
            tasks,
            decision=decision,
            skill_mode=skill_mode,
            explicit_skill_key=explicit_skill_key,
        )
        policy = self.policy.build(
            tasks,
            decision=decision,
            negative_action=classification.negative_action,
            has_open_proposal=context.has_open_proposal,
        )
        missing = tuple(slot for task in tasks for slot in task.missing_slots)
        pending = bool(routing.pending)
        clarification = self._clarification(decision, tasks, routing, reason)
        status = self._status_text(decision, tasks, pending, missing)
        return IntentResolution(
            resolution_id=uuid4().hex,
            feature_mode=mode,  # type: ignore[arg-type]
            applied=mode == "ENABLED",
            classifier_method=classification.method,
            problem_types=classification.problem_types,
            candidate_intents=tuple(item.intent_key for item in classification.candidates),
            resolved_intents=tuple(task.intent_key for task in tasks),
            tasks=tasks,
            decision=decision,
            missing_slots=tuple(dict.fromkeys(missing)),
            context_refs=context.refs,
            routing_plan=routing,
            tool_policy=policy,
            public_status=status,
            clarification=clarification,
            pending=pending,
            cancel_pending=False,
            negative_action=classification.negative_action,
            fallback_reason=classification.fallback_reason or reason,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            model_usage=classification.llm_usage,
            llm_called=classification.llm_called,
        )

    def _disabled(self, started: float) -> IntentResolution:
        return IntentResolution(
            resolution_id=uuid4().hex,
            feature_mode="DISABLED",
            applied=False,
            classifier_method="DISABLED",
            decision="UNKNOWN",
            routing_plan=RoutingPlan(reason="Intent V15 未启用，继续原路由"),
            tool_policy=ToolPolicy(reason="未启用理解层，写门禁仍由原治理负责"),
            public_status="",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def _cancelled(self, started: float) -> IntentResolution:
        return IntentResolution(
            resolution_id=uuid4().hex,
            feature_mode=intent_mode(),
            applied=intent_applied(),
            classifier_method="PENDING",
            problem_types=("CHAT",),
            resolved_intents=("general.chat",),
            decision="CLEAR",
            public_status="已取消待补充任务",
            clarification="已取消本次参数补充，可以重新描述任务。",
            cancel_pending=True,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    @staticmethod
    def _status_text(decision: str, tasks: tuple, pending: bool, missing: tuple[str, ...]) -> str:
        names = [task.name for task in tasks]
        if decision == "AMBIGUOUS":
            return "需要澄清：请说明查询的是客户还是员工，或其他具体对象"
        if pending or (decision == "INSUFFICIENT" and missing):
            label = "、".join(missing[:4]) if missing else "关键信息"
            prefix = "、".join(names) if names else "当前任务"
            return f"需要补充：{label}（{prefix}）"
        if not names:
            return "未识别到明确业务意图"
        if len(names) == 1:
            return f"已识别：{names[0]}"
        return f"已识别：{' + '.join(names)}"

    @staticmethod
    def _clarification(decision: str, tasks: tuple, routing: RoutingPlan, reason: str) -> str | None:
        if not routing.clarify:
            return None
        if decision == "AMBIGUOUS":
            return "我还不能确定你要查的对象。请补充是客户、员工、供应商，还是给出具体单号/SKU。"
        missing = [slot for task in tasks for slot in task.missing_slots]
        if "sku_code" in missing:
            return "请先提供要分析的 SKU 编号；如果有日期范围也可以一起补充。"
        if any(task.intent_key == "procurement.create_draft" for task in tasks):
            return "创建采购草稿需要供应商、仓库和采购商品（SKU 与数量）。请先提供这些信息。"
        if any(task.intent_key.startswith("product.") for task in tasks):
            return "请说明是哪一个商品，例如 SKU 编号或商品名称。"
        if missing:
            return f"还需要补充：{'、'.join(dict.fromkeys(missing))}。"
        return reason
