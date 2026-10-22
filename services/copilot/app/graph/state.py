from typing import TypedDict

from app.ai.types import ModelMessage, ModelToolCall, ModelUsage


class CopilotState(TypedDict):
    messages: list[ModelMessage]
    answer: str
    usage: ModelUsage | None
    pending_tool_calls: list[ModelToolCall]
    tool_rounds: int
