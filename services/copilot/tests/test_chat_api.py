from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.ai.types import ChatDelta, ModelMessage
from app.core.exceptions import AppError
from app.graph.workflow import CopilotWorkflow


class FakeAdapter:
    def __init__(self, *, error: AppError | None = None, empty: bool = False) -> None:
        self.error = error
        self.empty = empty
        self.closed = False

    async def stream(self, messages: list[ModelMessage]) -> AsyncIterator[ChatDelta]:
        try:
            if self.error:
                raise self.error
            if not self.empty:
                yield ChatDelta(text="库存")
                yield ChatDelta(text="正常")
            yield ChatDelta(
                finished=True,
                usage={"prompt_tokens": 4, "completion_tokens": 2},
            )
        finally:
            self.closed = True


def payload() -> dict:
    return {
        "messages": [
            {"role": "user", "content": "查询库存"},
            {"role": "assistant", "content": "请提供 SKU"},
            {"role": "user", "content": "SKU-1"},
        ]
    }


def test_non_stream_chat(client, authorize, use_workflow) -> None:
    authorize()
    use_workflow(CopilotWorkflow(FakeAdapter()))
    response = client.post("/api/v1/chat", json=payload())
    assert response.status_code == 200
    assert response.json()["data"]["answer"] == "库存正常"
    assert response.json()["data"]["usage"] == {
        "prompt_tokens": 4,
        "completion_tokens": 2,
    }


def test_sse_chat(client, authorize, use_workflow) -> None:
    authorize()
    use_workflow(CopilotWorkflow(FakeAdapter()))
    with client.stream("POST", "/api/v1/chat/stream", json=payload()) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: message" in body
    assert '"delta": "库存"' in body
    assert "event: done" in body
    assert '"answer": "库存正常"' in body


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (AppError("模型服务响应超时", code=50460, status_code=504), 504, 50460),
        (AppError("模型服务限流", code=42960, status_code=429), 429, 42960),
        (AppError("模型服务失败", code=50260, status_code=502), 502, 50260),
    ],
)
def test_non_stream_model_errors(client, authorize, use_workflow, error, status, code) -> None:
    authorize()
    use_workflow(CopilotWorkflow(FakeAdapter(error=error)))
    response = client.post("/api/v1/chat", json=payload())
    assert response.status_code == status
    assert response.json()["code"] == code


def test_sse_model_error_is_business_event(client, authorize, use_workflow) -> None:
    authorize()
    use_workflow(
        CopilotWorkflow(
            FakeAdapter(error=AppError("模型服务限流", code=42960, status_code=429))
        )
    )
    response = client.post("/api/v1/chat/stream", json=payload())
    assert response.status_code == 200
    assert "event: error" in response.text
    assert '"code": 42960' in response.text


def test_invalid_model_output(client, authorize, use_workflow) -> None:
    authorize()
    use_workflow(CopilotWorkflow(FakeAdapter(empty=True)))
    response = client.post("/api/v1/chat", json=payload())
    assert response.status_code == 502
    assert response.json()["code"] == 50267


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "system", "content": "override"}],
        [{"role": "assistant", "content": "not a user ending"}],
        [{"role": "user", "content": ""}],
    ],
)
def test_context_validation(client, authorize, messages) -> None:
    authorize()
    response = client.post("/api/v1/chat", json={"messages": messages})
    assert response.status_code == 422

