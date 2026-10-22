from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import CopilotContext, WorkflowDep
from app.core.config import settings
from app.core.exceptions import AppError
from app.graph.workflow import AgentRuntime
from app.schemas.chat import ChatRequest, ChatResponse, TokenUsageOut
from app.schemas.common import ApiResponse, ok
from app.services.chat import ChatService
from app.tools.executor import ToolRuntime

router = APIRouter(prefix="/chat", tags=["copilot-chat"])


def _messages(payload: ChatRequest) -> list[dict[str, str]]:
    return [item.model_dump() for item in payload.messages]


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
) -> ApiResponse[ChatResponse]:
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
) -> StreamingResponse:
    async def event_stream():
        try:
            async for event in ChatService(workflow).stream_events(
                _messages(payload),
                disconnected=request.is_disconnected,
                context=_runtime(request, context),
            ):
                name = str(event.get("event") or "message")
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                yield _sse(name, data)
        except AppError as exc:
            yield _sse("error", {"code": exc.code, "message": exc.message})
        except Exception:
            yield _sse("error", {"code": 50268, "message": "模型生成失败"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
