"""确定性模拟客户端，测试不依赖真实模型计费。"""

from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncIterator

from app.ai.types import ChatDelta, RerankHit
from app.core.config import settings
from app.core.exceptions import AppError


def _unit_vector(text: str) -> list[float]:
    """按字符频次构造确定性向量，相近文本更可能近邻。"""
    dim = settings.embedding_dimensions
    values = [0.05] * dim
    encoded = text.encode("utf-8")
    for index, byte in enumerate(encoded):
        values[(byte + index) % dim] += 1.0
    digest = hashlib.sha256(encoded).digest()
    for index, byte in enumerate(digest[:dim]):
        values[index] += byte / 255.0
    norm = math.sqrt(sum(item * item for item in values)) or 1.0
    return [item / norm for item in values]


class MockEmbeddingClient:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if any(item == "__DIM_MISMATCH__" for item in texts):
            return [[0.1, 0.2] for _ in texts]
        return [_unit_vector(text) for text in texts]


class MockChatClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[ChatDelta]:
        if self.fail:
            raise AppError("模拟聊天服务不可用", code=50201, status_code=502)
        system = next((item["content"] for item in messages if item.get("role") == "system"), "")
        question = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
        if "评测裁判" in system:
            if "__INVALID_JSON__" in question:
                answer = "not-json"
            else:
                answer = (
                    '{"faithfulness": 0.8, "answer_relevancy": 0.7, '
                    '"answer_correctness": 0.6, "refused": false, '
                    '"false_premise_identified": null, "correction_correctness": null, '
                    '"explanation": "mock-judge"}'
                )
        else:
            answer = "根据知识库证据，相关说明如下。证据不足的部分不会编造。"
            if "无结果" in question:
                answer = "知识库中没有足够依据回答该问题。"
        for char in answer:
            yield ChatDelta(text=char)
        yield ChatDelta(finished=True, prompt_tokens=12, completion_tokens=len(answer))


class MockRerankClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def rerank(self, query: str, documents: list[str]) -> list[RerankHit]:
        if self.fail:
            raise AppError("模拟 Rerank 失败", code=50202, status_code=502)
        scored = []
        needle = query.strip()
        for index, document in enumerate(documents):
            score = document.count(needle) / max(len(document), 1)
            if needle and needle in document:
                score += 1.0
            scored.append(RerankHit(index=index, score=score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored
