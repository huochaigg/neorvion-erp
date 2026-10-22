from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.ai.errors import classify_model_http_error, describe_model_transport
from app.ai.types import (
    ChatDelta,
    ModelMessage,
    ModelToolCall,
    ModelToolDefinition,
    ModelUsage,
)
from app.core.exceptions import AppError


class OpenAICompatChatAdapter:
    """DeepSeek、百炼等 OpenAI-compatible Chat Completions 的统一适配器。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.transport = transport

    async def stream(
        self,
        messages: list[ModelMessage],
        *,
        tools: list[ModelToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ChatDelta]:
        if not self.api_key:
            raise AppError("未配置 Chat API Key", code=50361, status_code=503)
        if not self.base_url:
            raise AppError("未配置 Chat Base URL", code=50361, status_code=503)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": self.max_output_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        prompt_tokens = None
        completion_tokens = None
        pending_calls: dict[int, dict[str, str]] = {}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise classify_model_http_error(
                            response.status_code,
                            body.decode("utf-8", errors="replace"),
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            usage: ModelUsage = {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                            }
                            yield ChatDelta(
                                finished=True,
                                usage=usage,
                                tool_calls=self._tool_calls(pending_calls),
                            )
                            return
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        raw_usage = chunk.get("usage") or {}
                        if isinstance(raw_usage, dict) and raw_usage:
                            prompt_tokens = raw_usage.get("prompt_tokens", prompt_tokens)
                            completion_tokens = raw_usage.get(
                                "completion_tokens", completion_tokens
                            )
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content") or ""
                        if text:
                            yield ChatDelta(text=str(text))
                        for raw_call in delta.get("tool_calls") or []:
                            index = int(raw_call.get("index") or 0)
                            current = pending_calls.setdefault(
                                index, {"id": "", "name": "", "arguments": ""}
                            )
                            current["id"] += str(raw_call.get("id") or "")
                            function = raw_call.get("function") or {}
                            current["name"] += str(function.get("name") or "")
                            current["arguments"] += str(function.get("arguments") or "")
                    usage = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    }
                    yield ChatDelta(
                        finished=True,
                        usage=usage,
                        tool_calls=self._tool_calls(pending_calls),
                    )
        except AppError:
            raise
        except httpx.HTTPError as exc:
            raise describe_model_transport(exc) from exc

    @staticmethod
    def _tool_calls(pending: dict[int, dict[str, str]]) -> tuple[ModelToolCall, ...]:
        """把 OpenAI 分片的函数名和参数合并，参数 JSON 留给工具层严格校验。"""
        return tuple(
            ModelToolCall(
                id=item["id"] or f"tool-{index}",
                name=item["name"],
                arguments=item["arguments"],
            )
            for index, item in sorted(pending.items())
        )
