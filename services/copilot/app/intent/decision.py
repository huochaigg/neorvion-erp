"""意图裁决：CLEAR / AMBIGUOUS / INSUFFICIENT / UNKNOWN。CLEAR 不等于可执行。"""

from __future__ import annotations

from app.intent.registry import IntentRegistry, get_intent_registry
from app.intent.schemas import (
    ClassificationResult,
    ConversationContext,
    IntentCandidate,
    IntentDecision,
    ResolvedTask,
)

_MUTEX_GROUPS = (
    frozenset({"party.lookup"}),
    frozenset({"inventory.query", "inventory.coverage_analysis", "inventory.risk_analysis"}),
)


class DecisionEngine:
    """
    输入：分类候选与上下文。
    输出：决策状态、保留任务和缺失槽位。
    流程：校验 Registry → 区分多意图与互斥歧义 → 检查槽位 → 安全降级。
    边界：不使用单一 confidence 阈值作为唯一门槛；不把 CLEAR 当成授权。
    """

    def __init__(self, registry: IntentRegistry | None = None) -> None:
        self.registry = registry or get_intent_registry()

    def decide(
        self, classification: ClassificationResult, context: ConversationContext
    ) -> tuple[IntentDecision, tuple[ResolvedTask, ...], str]:
        valid: list[IntentCandidate] = []
        for item in classification.candidates:
            if self.registry.get(item.intent_key) is None:
                continue
            if classification.negative_action and item.problem_type == "ACTION":
                continue
            valid.append(item)
        if classification.unknown and not valid:
            return "UNKNOWN", (), "无法合理识别用户目标"
        if not valid:
            return "UNKNOWN", (), "候选意图均不在 Registry 或被安全策略丢弃"
        if self._ambiguous_person(valid, context):
            return "AMBIGUOUS", self._tasks(valid, "AMBIGUOUS"), "查询对象可能是客户或员工，需要澄清"
        if self._mutex(valid) and not classification.multi_task:
            return "AMBIGUOUS", self._tasks(valid, "AMBIGUOUS"), "存在多个互斥候选"
        tasks = self._tasks(self._dedupe(valid), "CLEAR")
        needs_slots = any(
            task.missing_slots and task.problem_type in {"ACTION", "ANALYZE"} for task in tasks
        )
        if needs_slots:
            return "INSUFFICIENT", tasks, "意图明确但缺少后续处理所需信息"
        if context.context_dependent and not any(task.slots for task in tasks) and len(tasks) == 1:
            only = tasks[0]
            if only.intent_key in {
                "product.price_query",
                "product.price_change",
                "sales.order_query",
                "inventory.query",
            }:
                return "INSUFFICIENT", tasks, "缺少被指代的业务对象"
        if any(task.intent_key == "product.price_change" and not task.slots for task in tasks):
            return "INSUFFICIENT", tasks, "改价缺少具体商品，不能执行"
        if any(not task.executable and task.problem_type == "ACTION" for task in tasks):
            return "CLEAR", tasks, "已识别但当前没有对应执行能力"
        return "CLEAR", tasks, "意图明确且结构合法"

    def _tasks(self, candidates: list[IntentCandidate], _decision: str) -> tuple[ResolvedTask, ...]:
        output: list[ResolvedTask] = []
        for index, item in enumerate(candidates, start=1):
            definition = self.registry.require(item.intent_key)
            output.append(
                ResolvedTask(
                    task_id=f"t{index}",
                    intent_key=item.intent_key,
                    name=definition.name,
                    problem_type=item.problem_type,
                    domain=item.domain,
                    slots={slot.name: slot.value for slot in item.slots},
                    missing_slots=item.missing_slots,
                    candidate_agents=definition.candidate_agents,
                    candidate_skills=definition.candidate_skills,
                    capability_hints=definition.capability_hints,
                    risk_hint=definition.risk_hint,
                    executable=definition.executable,
                    source=item.source,
                )
            )
        return tuple(output)

    @staticmethod
    def _dedupe(candidates: list[IntentCandidate]) -> list[IntentCandidate]:
        seen: set[str] = set()
        output: list[IntentCandidate] = []
        for item in candidates:
            if item.intent_key in seen:
                continue
            seen.add(item.intent_key)
            output.append(item)
        return output

    @staticmethod
    def _mutex(candidates: list[IntentCandidate]) -> bool:
        keys = {item.intent_key for item in candidates}
        if "party.lookup" in keys and len(candidates) == 1:
            return True
        inventory = keys & {"inventory.query", "inventory.coverage_analysis", "inventory.risk_analysis"}
        return len(inventory) > 1 and len(candidates) == len(inventory)

    @staticmethod
    def _ambiguous_person(candidates: list[IntentCandidate], context: ConversationContext) -> bool:
        del context
        return len(candidates) == 1 and candidates[0].intent_key == "party.lookup"
