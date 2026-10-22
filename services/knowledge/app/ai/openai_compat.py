"""OpenAI 兼容 Embedding / Chat / Rerank HTTP 客户端。密钥只留在服务端。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.ai.errors import classify_model_http_error, describe_embedding_transport
from app.ai.types import ChatDelta, RerankHit
from app.core.config import settings
from app.core.exceptions import AppError

_classify_http_error = classify_model_http_error


class OpenAICompatEmbeddingClient:
    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors, _usage = await self.embed_with_usage(texts)
        return vectors

    async def embed_with_usage(self, texts: list[str]) -> tuple[list[list[float]], dict[str, Any] | None]:
        if not self.api_key:
            raise AppError("未配置 Embedding API Key", code=50360, status_code=503)
        if not self.base_url:
            raise AppError("未配置 Embedding Base URL", code=50360, status_code=503)
        payload = {"model": self.model, "input": texts}
        if settings.embedding_dimensions:
            payload["dimensions"] = settings.embedding_dimensions
        data = await self._post("/embeddings", payload)
        items = sorted(data.get("data") or [], key=lambda row: int(row.get("index") or 0))
        vectors = [list(row.get("embedding") or []) for row in items]
        if len(vectors) != len(texts):
            raise AppError("Embedding 返回条数与输入不一致", code=50261, status_code=502)
        actual_dim = len(vectors[0]) if vectors else 0
        if actual_dim != settings.embedding_dimensions:
            raise AppError(
                f"向量维度与配置不一致：期望 {settings.embedding_dimensions}，实际 {actual_dim}",
                code=40090,
                status_code=400,
            )
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        return vectors, usage

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:
            raise describe_embedding_transport(exc) from exc
        if response.status_code >= 400:
            raise _classify_http_error(response.status_code, response.text)
        return response.json()


class OpenAICompatChatClient:
    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[ChatDelta]:
        if not self.api_key:
            raise AppError("未配置 Chat API Key", code=50361, status_code=503)
        url = f"{self.base_url}/chat/completions"
        payload = {"model": self.model, "messages": messages, "stream": True, "stream_options": {"include_usage": True}}
        if "deepseek.com" in self.base_url or self.model.startswith("deepseek"):
            payload["thinking"] = {"type": "disabled"}
        try:
            async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise _classify_http_error(response.status_code, body.decode("utf-8", errors="replace"))
                    prompt_tokens = None
                    completion_tokens = None
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            yield ChatDelta(
                                finished=True,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                            )
                            return
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        usage = chunk.get("usage") or {}
                        if usage:
                            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                            completion_tokens = usage.get("completion_tokens", completion_tokens)
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}).get("content") or ""
                        if delta:
                            yield ChatDelta(text=delta)
                    yield ChatDelta(
                        finished=True,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
        except AppError:
            raise
        except httpx.TimeoutException as exc:
            raise AppError("模型服务超时", code=50460, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("无法连接 Chat 服务，请检查 Base URL", code=50262, status_code=502) from exc


class OpenAICompatRerankClient:
    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def rerank(self, query: str, documents: list[str]) -> list[RerankHit]:
        if not self.api_key or not self.model:
            raise AppError("未配置 Rerank 模型", code=50362, status_code=503)
        url = f"{self.base_url}/rerank"
        payload = {"model": self.model, "query": query, "documents": documents}
        try:
            async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.TimeoutException as exc:
            raise AppError("Rerank 超时", code=50460, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("无法连接 Rerank 服务", code=50262, status_code=502) from exc
        if response.status_code >= 400:
            raise _classify_http_error(response.status_code, response.text)
        data = response.json()
        results = data.get("results") or data.get("data") or []
        hits: list[RerankHit] = []
        for row in results:
            index = int(row.get("index") if row.get("index") is not None else row.get("document_index") or 0)
            score = float(row.get("relevance_score") if row.get("relevance_score") is not None else row.get("score") or 0)
            hits.append(RerankHit(index=index, score=score))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits
