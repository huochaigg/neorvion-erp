"""规则快速路径 + LLM 兜底。V15 不引入 Embedding 或双通道融合。"""

from __future__ import annotations

from app.ai.types import ChatAdapter
from app.intent.classifiers.llm import LlmIntentClassifier
from app.intent.classifiers.rules import RulesIntentClassifier
from app.intent.flags import intent_llm_allowed
from app.intent.registry import IntentRegistry, get_intent_registry
from app.intent.schemas import ClassificationResult, ConversationContext


class HybridIntentClassifier:
    """
    输入：租户隔离后的对话上下文与可选模型适配器。
    输出：带 method 标记的分类结果。
    流程：规则召回 → 满足快速通过则返回 → 否则 LLM → 校验失败则安全降级。
    边界：分类失败不得产生 ACTION 写意图；UNKNOWN 不得被改写成某个业务意图。
    """

    def __init__(self, registry: IntentRegistry | None = None) -> None:
        self.registry = registry or get_intent_registry()
        self.rules = RulesIntentClassifier(self.registry)
        self.llm = LlmIntentClassifier(self.registry)

    async def classify(
        self,
        context: ConversationContext,
        *,
        adapter: ChatAdapter | None = None,
        allow_llm: bool | None = None,
    ) -> ClassificationResult:
        rules_result = await self.rules.classify(context)
        if self.rules.fast_path_allowed(rules_result, context):
            return rules_result
        if adapter is None or not (allow_llm if allow_llm is not None else intent_llm_allowed()):
            if rules_result.candidates:
                return rules_result.model_copy(
                    update={"method": "HYBRID", "fallback_reason": "llm_skipped"}
                )
            return ClassificationResult(
                method="FALLBACK",
                problem_types=("UNKNOWN",) if not rules_result.problem_types else rules_result.problem_types,
                candidates=rules_result.candidates,
                negative_action=rules_result.negative_action,
                how_to=rules_result.how_to,
                multi_task=rules_result.multi_task,
                unknown=not rules_result.candidates,
                fallback_reason="classifier_unavailable",
            )
        llm_result = await self.llm.classify(context, adapter=adapter)
        if llm_result.candidates:
            return llm_result.model_copy(update={"method": "HYBRID"})
        if rules_result.candidates:
            return rules_result.model_copy(
                update={
                    "method": "HYBRID",
                    "llm_called": llm_result.llm_called,
                    "llm_usage": llm_result.llm_usage,
                    "fallback_reason": llm_result.fallback_reason or "llm_empty",
                }
            )
        return llm_result.model_copy(
            update={
                "method": "FALLBACK",
                "unknown": True,
                "fallback_reason": llm_result.fallback_reason or "unknown",
            }
        )
