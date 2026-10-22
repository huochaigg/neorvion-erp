from typing import TypedDict

from app.ai.types import ModelMessage, ModelUsage


class CopilotState(TypedDict):
    messages: list[ModelMessage]
    answer: str
    usage: ModelUsage | None

