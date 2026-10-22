from __future__ import annotations

import httpx
import pytest
from app.ai.openai_compat import OpenAICompatChatAdapter
from app.core.exceptions import AppError


def adapter(transport: httpx.AsyncBaseTransport) -> OpenAICompatChatAdapter:
    return OpenAICompatChatAdapter(
        base_url="https://models.test/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=1,
        max_output_tokens=64,
        transport=transport,
    )


@pytest.mark.asyncio
async def test_openai_compatible_stream() -> None:
    body = (
        'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n\n'
        "data: [DONE]\n\n"
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    )
    items = [
        item
        async for item in adapter(transport).stream(
            [{"role": "user", "content": "hi"}]
        )
    ]
    assert "".join(item.text for item in items) == "你好"
    assert items[-1].finished is True
    assert items[-1].usage == {"prompt_tokens": 3, "completion_tokens": 2}


@pytest.mark.parametrize(("status", "expected_code"), [(429, 42960), (500, 50260)])
@pytest.mark.asyncio
async def test_openai_compatible_http_errors(status: int, expected_code: int) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": {"message": "failed"}})
    )
    with pytest.raises(AppError) as captured:
        _ = [
            item
            async for item in adapter(transport).stream(
                [{"role": "user", "content": "hi"}]
            )
        ]
    assert captured.value.code == expected_code


@pytest.mark.asyncio
async def test_openai_compatible_timeout() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(AppError) as captured:
        _ = [
            item
            async for item in adapter(httpx.MockTransport(timeout)).stream(
                [{"role": "user", "content": "hi"}]
            )
        ]
    assert captured.value.code == 50462

