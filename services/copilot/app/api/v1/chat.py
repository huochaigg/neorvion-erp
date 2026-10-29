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
from app.erp.client import get_erp_client
from app.graph.workflow import AgentRuntime
from app.mcp.gateway import McpGateway
from app.schemas.chat import ChatRequest, ChatResponse, TokenUsageOut
from app.schemas.common import ApiResponse, ok
from app.services.action_proposals import ActionProposalService
from app.services.chat import ChatService
from app.services.persistent_chat import PersistentChatService
from app.services.quotas import (
    RuntimeGovernance,
    enforce_runtime_governance,
    reserve_chat_quota,
    usage_tokens,
)
from app.tools.executor import ToolRuntime

router = APIRouter(prefix="/chat", tags=["copilot-chat"])


def _messages(payload: ChatRequest) -> list[ModelMessage]:
    return [{"role": item.role, "content": item.content} for item in payload.messages]


def _event_data(event: dict) -> dict:
    raw = event.get("data")
    return raw if isinstance(raw, dict) else {}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _runtime(
    request: Request,
    context: CopilotContext,
    db: DbSession,
    *,
    conversation_id: int | None = None,
    source_message_id: int | None = None,
    governance: RuntimeGovernance | None = None,
    mcp_gateway: McpGateway | None = None,
) -> AgentRuntime:
    audiences = frozenset(getattr(request.state, "jwt_audiences", ()))
    access_token = str(getattr(request.state, "access_token", ""))
    request_id = str(getattr(request.state, "request_id", ""))
    proposal_service = None
    if conversation_id is not None:
        proposal_service = ActionProposalService(
            cast(AsyncSession, db),
            context,
            erp_client=get_erp_client(),
            access_token=access_token,
            request_id=request_id,
        )
    return AgentRuntime(
        tools=ToolRuntime(
            tenant=context,
            access_token=access_token,
            erp_audience_authorized=settings.erp_jwt_audience in audiences,
            knowledge_audience_authorized=settings.knowledge_jwt_audience in audiences,
            request_id=request_id,
            proposal_service=proposal_service,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            allowed_tools=governance.allowed_tools if governance else None,
            max_calls_override=governance.max_tool_calls if governance else None,
            global_call_limit=governance.max_tool_calls if governance else None,
            mcp_gateway=mcp_gateway,
        ),
        allow_multi_agent=governance.allow_multi_agent if governance else True,
    )


@router.post("", response_model=ApiResponse[ChatResponse], summary="非流式对话")
async def chat(
    payload: ChatRequest,
    request: Request,
    context: CopilotContext,
    workflow: WorkflowDep,
    db: DbSession,
) -> ApiResponse[ChatResponse]:
    governance = await enforce_runtime_governance(cast(AsyncSession, db), context.tenant_id, "CHAT")
    reservation = await reserve_chat_quota(
        cast(AsyncSession, db), context.tenant_id, _estimated_tokens(payload)
    )
    mcp_gateway = await McpGateway.load(
        cast(AsyncSession, db),
        context,
        allowed_tools=governance.allowed_tools,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    usage = None
    try:
        if payload.conversation_id is not None:
            service = PersistentChatService(cast(AsyncSession, db), context, workflow)
            turn = await service.prepare(
                payload.conversation_id,
                payload.message or "",
                payload.client_request_id or "",
                str(getattr(request.state, "request_id", "") or uuid4().hex),
            )
            answer = ""
            async for event in service.events(
                turn,
                _runtime(
                    request,
                    context,
                    db,
                    conversation_id=turn.conversation_id,
                    source_message_id=turn.message_id,
                    governance=governance,
                    mcp_gateway=mcp_gateway,
                ),
                lambda: _false(),
            ):
                if event["event"] == "done":
                    answer = str(event["data"].get("answer") or "")
                    usage = event["data"].get("usage")
            response = ChatResponse(
                answer=answer,
                model=settings.chat_model,
                usage=TokenUsageOut.model_validate(usage) if isinstance(usage, dict) else None,
                conversation_id=turn.conversation_id,
                message_id=turn.message_id,
                request_id=turn.request_id,
            )
        else:
            answer, usage = await ChatService(workflow).complete(
                _messages(payload),
                context=_runtime(
                    request,
                    context,
                    db,
                    governance=governance,
                    mcp_gateway=mcp_gateway,
                ),
            )
            response = ChatResponse(
                answer=answer,
                model=settings.chat_model,
                usage=TokenUsageOut.model_validate(usage) if usage is not None else None,
            )
        await reservation.settle(usage_tokens(usage))
        return ok(response)
    except BaseException:
        await reservation.cancel()
        raise


@router.post("/stream", summary="SSE 流式对话")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    context: CopilotContext,
    workflow: WorkflowDep,
    db: DbSession,
) -> StreamingResponse:
    stream_request_id = str(getattr(request.state, "request_id", "") or uuid4().hex)
    governance = await enforce_runtime_governance(cast(AsyncSession, db), context.tenant_id, "CHAT")
    reservation = await reserve_chat_quota(
        cast(AsyncSession, db), context.tenant_id, _estimated_tokens(payload)
    )
    mcp_gateway = await McpGateway.load(
        cast(AsyncSession, db),
        context,
        allowed_tools=governance.allowed_tools,
        request_id=stream_request_id,
    )

    async def event_stream():
        persistent_turn = None
        final_usage = None
        completed = False
        try:
            if payload.conversation_id is not None:
                service = PersistentChatService(cast(AsyncSession, db), context, workflow)
                turn = await service.prepare(
                    payload.conversation_id,
                    payload.message or "",
                    payload.client_request_id or "",
                    stream_request_id,
                )
                persistent_turn = turn
                events = service.events(
                    turn,
                    _runtime(
                        request,
                        context,
                        db,
                        conversation_id=turn.conversation_id,
                        source_message_id=turn.message_id,
                        governance=governance,
                        mcp_gateway=mcp_gateway,
                    ),
                    request.is_disconnected,
                )
            else:
                events = ChatService(workflow).stream_events(
                    _messages(payload),
                    disconnected=request.is_disconnected,
                    context=_runtime(
                        request,
                        context,
                        db,
                        governance=governance,
                        mcp_gateway=mcp_gateway,
                    ),
                )
            async for event in events:
                name = str(event.get("event") or "message")
                data = _event_data(event)
                if name == "done":
                    final_usage = data.get("usage")
                    completed = True
                data.setdefault("request_id", stream_request_id)
                yield _sse(name, data)
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
            yield _sse(
                "error",
                {"code": exc.code, "message": exc.message, "request_id": stream_request_id} | ids,
            )
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
            yield _sse(
                "error",
                {"code": 50268, "message": "模型生成失败", "request_id": stream_request_id} | ids,
            )
        finally:
            if completed:
                await reservation.settle(usage_tokens(final_usage))
            else:
                await reservation.cancel()

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


def _estimated_tokens(payload: ChatRequest) -> int:
    text_size = len(payload.message or "") + sum(len(item.content) for item in payload.messages)
    return max(1, (text_size + 2) // 3) + settings.chat_max_output_tokens
