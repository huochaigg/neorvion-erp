from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable

from app.ai.types import ModelMessage
from app.graph.workflow import AgentRuntime, CopilotWorkflow


class ChatService:
    def __init__(self, workflow: CopilotWorkflow) -> None:
        self.workflow = workflow

    async def complete(self, messages: list[ModelMessage], *, context: AgentRuntime):
        return await self.workflow.invoke(messages, context=context)

    async def stream_events(
        self,
        messages: list[ModelMessage],
        *,
        disconnected: Callable[[], Awaitable[bool]],
        context: AgentRuntime,
    ) -> AsyncGenerator[dict, None]:
        """消费图事件；客户端断开时主动关闭图迭代器以释放上游 HTTP 流。"""
        context.disconnected = disconnected
        stream = self.workflow.stream(messages, context=context)
        try:
            async for event in stream:
                if await disconnected():
                    return
                yield event
        finally:
            await stream.aclose()
