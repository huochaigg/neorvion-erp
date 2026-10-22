from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, Protocol, TypedDict


class ModelFunctionCall(TypedDict):
    name: str
    arguments: str


class ModelToolCallPayload(TypedDict):
    id: str
    type: Literal["function"]
    function: ModelFunctionCall


class ModelMessage(TypedDict):
    role: str
    content: str | None
    tool_calls: NotRequired[list[ModelToolCallPayload]]
    tool_call_id: NotRequired[str]


class ModelToolDefinition(TypedDict):
    type: Literal["function"]
    function: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    id: str
    name: str
    arguments: str


class ModelUsage(TypedDict):
    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass(frozen=True, slots=True)
class ChatDelta:
    text: str = ""
    usage: ModelUsage | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()
    finished: bool = False


class ChatAdapter(Protocol):
    def stream(
        self,
        messages: list[ModelMessage],
        *,
        tools: list[ModelToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ChatDelta]:
        """以统一增量格式调用模型；密钥、HTTP 协议和供应商差异不得泄露到路由。"""
        ...
