from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.core.exceptions import AppError
from app.graph.workflow import AgentRuntime
from app.schemas.chat import ChatMessageIn, ChatRequest
from app.services.persistent_chat import PersistentChatService, PersistentTurn


def row(role: str, content: str, *, status: str = "COMPLETED", protocol=None):
    return SimpleNamespace(role=role, content=content, status=status, protocol_data=protocol)


def test_persistent_request_requires_idempotency_fields() -> None:
    with pytest.raises(ValueError):
        ChatRequest(
            conversation_id=1,
            messages=[ChatMessageIn(role="user", content="伪造历史")],
        )


def test_history_keeps_tool_call_and_result_together() -> None:
    protocol = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "get_inventory", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "queried_at=now result"},
        {"role": "assistant", "content": "库存为 7"},
    ]
    history = PersistentChatService._build_history(
        [row("user", "查询库存"), row("assistant", "库存为 7", protocol=protocol)]
    )
    assert [item["role"] for item in history] == ["user", "assistant", "tool", "assistant"]
    tool_calls = history[1].get("tool_calls") or []
    assert history[2].get("tool_call_id") == tool_calls[0]["id"]


class FakeSession:
    commits = 0

    async def commit(self):
        self.commits += 1


class FakeRepo:
    def __init__(self):
        self.events = []
        self.finished = []

    async def record_tool_event(self, conversation_id, message_id, event, data):
        self.events.append((event, data))

    async def record_evidence(self, conversation_id, message_id, data):
        self.events.append(("evidence", data))

    async def finish_message(self, message_id, **values):
        self.finished.append(values)


class FakeWorkflow:
    async def stream(self, messages, *, context):
        context.protocol_messages.extend([{"role": "assistant", "content": "完成"}])
        yield {"event": "tool_start", "data": {"tool_call_id": "c1", "name": "get_inventory"}}
        yield {"event": "tool_end", "data": {"tool_call_id": "c1", "name": "get_inventory", "duration_ms": 3}}
        yield {"event": "evidence", "data": {"tool_call_id": "c1", "citation_id": "E1"}}
        yield {"event": "message", "data": {"delta": "完成"}}
        yield {"event": "done", "data": {"answer": "完成"}}


class DisconnectWorkflow:
    async def stream(self, messages, *, context):
        del messages
        if await context.disconnected():
            raise AppError("客户端已断开", code=49900, status_code=499)
        yield {"event": "done", "data": {"answer": "不应到达"}}


@pytest.mark.asyncio
async def test_persistent_stream_records_tool_run_and_message() -> None:
    service = cast(Any, object.__new__(PersistentChatService))
    service.session = FakeSession()
    service.repo = FakeRepo()
    service.workflow = FakeWorkflow()

    async def connected():
        return False

    events = [
        item
        async for item in service.events(
            PersistentTurn(1, 2, "request-1", [{"role": "user", "content": "查库存"}]),
            AgentRuntime(protocol_messages=[]),
            connected,
        )
    ]
    assert [item["event"] for item in events] == [
        "run_start",
        "tool_start",
        "tool_end",
        "evidence",
        "message",
        "done",
    ]
    assert [item[0] for item in service.repo.events] == ["tool_start", "tool_end", "evidence"]
    assert service.repo.finished[-1]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_disconnected_stream_is_persisted_as_cancelled() -> None:
    service = cast(Any, object.__new__(PersistentChatService))
    service.session = FakeSession()
    service.repo = FakeRepo()
    service.workflow = DisconnectWorkflow()

    async def disconnected():
        return True

    with pytest.raises(AppError, match="客户端已断开"):
        async for _ in service.events(
            PersistentTurn(1, 2, "request-2", [{"role": "user", "content": "查库存"}]),
            AgentRuntime(protocol_messages=[]),
            disconnected,
        ):
            pass
    assert service.repo.finished[-1]["status"] == "CANCELLED"
    assert service.repo.finished[-1]["error_code"] == 49900
