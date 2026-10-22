from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, TypedDict


class ModelMessage(TypedDict):
    role: str
    content: str


class ModelUsage(TypedDict):
    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass(frozen=True, slots=True)
class ChatDelta:
    text: str = ""
    usage: ModelUsage | None = None
    finished: bool = False


class ChatAdapter(Protocol):
    def stream(self, messages: list[ModelMessage]) -> AsyncIterator[ChatDelta]:
        """以统一增量格式调用模型；密钥、HTTP 协议和供应商差异不得泄露到路由。"""
        ...

