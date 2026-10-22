from __future__ import annotations

from collections.abc import AsyncIterator

from app.ai.types import ChatDelta, ModelMessage, ModelToolDefinition


class MockChatAdapter:
    """本地与测试使用的确定性模型，不访问外部网络。"""

    async def stream(
        self,
        messages: list[ModelMessage],
        *,
        tools: list[ModelToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ChatDelta]:
        question = next(
            (
                str(item.get("content") or "")
                for item in reversed(messages)
                if item["role"] == "user"
            ),
            "",
        )
        answer = f"这是 Copilot V2 的模拟回答：{question[:80]}"
        for part in (answer[: len(answer) // 2], answer[len(answer) // 2 :]):
            if part:
                yield ChatDelta(text=part)
        yield ChatDelta(
            finished=True,
            usage={"prompt_tokens": 8, "completion_tokens": len(answer)},
        )
