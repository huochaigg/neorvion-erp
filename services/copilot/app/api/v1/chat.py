from __future__ import annotations

import json
from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ModelMessage
from app.api.deps import CopilotContext, DbSession, WorkflowDep
from app.core.config import settings
from app.core.exceptions import AppError
from app.graph.workflow import AgentRuntime
from app.schemas.chat import ChatRequest, ChatResponse, TokenUsageOut
from app.schemas.common import ApiResponse, ok
from app.services.chat import ChatService
from app.services.persistent_chat import PersistentChatService
from app.tools.executor import ToolRuntime

router = APIRouter(prefix="/chat", tags=["copilot-chat"])


def _messages(payload: ChatRequest) -> list[ModelMessage]:
    return [{"role": item.role, "content": item.content} for item in payload.messages]


def _event_data(event: dict) -> dict:
    raw = event.get("data")
    return raw if isinstance(raw, dict) else {}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _runtime(request: Request, context: CopilotContext) -> AgentRuntime:
    audiences = frozenset(getattr(request.state, "jwt_audiences", ()))
    return AgentRuntime(
        tools=ToolRuntime(
            tenant=context,
            access_token=str(getattr(request.state, "access_token", "")),
            erp_audience_authorized=settings.erp_jwt_audience in audiences,
            request_id=str(getattr(request.state, "request_id", "")),
        )
    )


@router.post("", response_model=ApiResponse[ChatResponse], summary="非流式对话")
async def chat(
    payload: ChatRequest,
    request: Request,
    context: CopilotContext,
    workflow: WorkflowDep,
    db: DbSession,
) -> ApiResponse[ChatResponse]:
    if payload.conversation_id is not None:
        service = PersistentChatService(cast(AsyncSession, db), context, workflow)
        turn = await service.prepare(
            payload.conversation_id,
            payload.message or "",
            payload.client_request_id or "",
            str(getattr(request.state, "request_id", "") or uuid4().hex),
        )
        answer = ""
        usage = None
        async for event in service.events(turn, _runtime(request, context), lambda: _false()):
            if event["event"] == "done":
                answer = str(event["data"].get("answer") or "")
                usage = event["data"].get("usage")
        return ok(ChatResponse(
            answer=answer, model=settings.chat_model,
            usage=TokenUsageOut(**usage) if isinstance(usage, dict) else None,
            conversation_id=turn.conversation_id, message_id=turn.message_id, request_id=turn.request_id,
        ))
    answer, usage = await ChatService(workflow).complete(
        _messages(payload), context=_runtime(request, context)
    )
    return ok(
        ChatResponse(
            answer=answer,
            model=settings.chat_model,
            usage=TokenUsageOut(**usage) if usage is not None else None,
        )
    )


@router.post("/stream", summary="SSE 流式对话")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    context: CopilotContext,
    workflow: WorkflowDep,
    db: DbSession,
) -> StreamingResponse:
    async def event_stream():
        persistent_turn = None
        try:
            if payload.conversation_id is not None:
                service = PersistentChatService(cast(AsyncSession, db), context, workflow)
                turn = await service.prepare(
                    payload.conversation_id, payload.message or "", payload.client_request_id or "",
                    str(getattr(request.state, "request_id", "") or uuid4().hex),
                )
                persistent_turn = turn
                events = service.events(turn, _runtime(request, context), request.is_disconnected)
            else:
                events = ChatService(workflow).stream_events(
                    _messages(payload), disconnected=request.is_disconnected, context=_runtime(request, context)
                )
            async for event in events:
                name = str(event.get("event") or "message")
                yield _sse(name, _event_data(event))
        except AppError as exc:
            ids = (
                {
                    "request_id": persistent_turn.request_id,
                    "conversation_id": persistent_turn.conversation_id,
                    "message_id": persistent_turn.message_id,
                }
                if persistent_turn is not None
                else {}
            )
            yield _sse("error", {"code": exc.code, "message": exc.message} | ids)
        except Exception:
            ids = (
                {
                    "request_id": persistent_turn.request_id,
                    "conversation_id": persistent_turn.conversation_id,
                    "message_id": persistent_turn.message_id,
                }
                if persistent_turn is not None
                else {}
            )
            yield _sse("error", {"code": 50268, "message": "模型生成失败"} | ids)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _false() -> bool:
    return False
