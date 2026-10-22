from __future__ import annotations

import pytest
from app.ai.types import ModelMessage
from app.services.chat import ChatService


class ClosingWorkflow:
    def __init__(self) -> None:
        self.closed = False

    async def stream(self, _messages: list[ModelMessage]):
        try:
            yield {"event": "message", "data": {"delta": "first"}}
            yield {"event": "message", "data": {"delta": "second"}}
        finally:
            self.closed = True


@pytest.mark.asyncio
async def test_disconnect_closes_graph_stream() -> None:
    workflow = ClosingWorkflow()

    async def disconnected() -> bool:
        return True

    events = [
        event
        async for event in ChatService(workflow).stream_events(
            [{"role": "user", "content": "hello"}],
            disconnected=disconnected,
        )
    ]
    assert events == []
    assert workflow.closed is True

