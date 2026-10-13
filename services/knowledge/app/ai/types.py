from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatDelta:
    text: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finished: bool = False


@dataclass(frozen=True)
class RerankHit:
    index: int
    score: float


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量。返回长度必须等于 texts，每条维度必须与配置一致。"""


class ChatClient(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[ChatDelta]:
        """流式生成。messages 为 OpenAI chat 格式。"""


class RerankClient(Protocol):
    async def rerank(self, query: str, documents: list[str]) -> list[RerankHit]:
        """按相关性重排。失败由调用方降级。"""
