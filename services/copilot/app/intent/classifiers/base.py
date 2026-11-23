from __future__ import annotations

from typing import Protocol

from app.ai.types import ChatAdapter
from app.intent.schemas import ClassificationResult, ConversationContext


class IntentClassifier(Protocol):
    """可扩展分类器接口。V15 实现规则与 LLM；后续可增加 Semantic Classifier。"""

    async def classify(
        self,
        context: ConversationContext,
        *,
        adapter: ChatAdapter | None = None,
    ) -> ClassificationResult:
        """
        输入：已按租户隔离的对话上下文。
        输出：候选意图与问题类型，不包含授权结论。
        边界：只能返回 Registry 中的 intent_key；失败时不得编造写操作意图。
        """
        ...
