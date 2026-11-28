from typing import cast

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CopilotContext, DbSession, WorkflowDep
from app.api.v1.chat import _sse, chat_stream, iter_message_sse
from app.core.config import settings
from app.knowledge.client import get_knowledge_client
from app.schemas.chat import ChatRequest
from app.schemas.common import ApiResponse, ok
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationListOut,
    ConversationMessageIn,
    ConversationOut,
    ConversationRename,
)
from app.services.conversations import ConversationService

router = APIRouter(prefix="/conversations", tags=["copilot-conversations"])


@router.post("", response_model=ApiResponse[ConversationOut])
async def create_conversation(payload: ConversationCreate, context: CopilotContext, db: DbSession):
    return ok(await ConversationService(cast(AsyncSession, db), context).create(payload.title))


@router.get("", response_model=ApiResponse[ConversationListOut])
async def list_conversations(
    context: CopilotContext,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=settings.conversation_page_size_max),
):
    return ok(await ConversationService(cast(AsyncSession, db), context).list(page, page_size))


@router.get(
    "/{conversation_id}", response_model=ApiResponse[ConversationDetailOut], summary="加载会话详情"
)
async def get_conversation(
    conversation_id: int, request: Request, context: CopilotContext, db: DbSession
):
    audiences = frozenset(getattr(request.state, "jwt_audiences", ()))
    service = ConversationService(
        cast(AsyncSession, db),
        context,
        knowledge_client=get_knowledge_client(),
        access_token=str(getattr(request.state, "access_token", "")),
        knowledge_audience_authorized=settings.knowledge_jwt_audience in audiences,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return ok(await service.get(conversation_id))


@router.get(
    "/{conversation_id}/messages/{message_id}/events",
    summary="订阅已有 Chat Run 的 SSE（不创建新消息）",
)
def _sse_chunk_is_terminal(chunk: str) -> bool:
    text = chunk if chunk.startswith("event:") else f"\n{chunk}"
    return "\nevent: done\n" in f"\n{text}" or "\nevent: error\n" in f"\n{text}"


async def _followup_subscribe_snapshot(context: CopilotContext, conversation_id: int, message_id: int):
    from app.db.session import open_tenant_session

    session = open_tenant_session(context.tenant_id)
    try:
        service = ConversationService(session, context)
        return await service.prepare_subscribe(conversation_id, message_id)
    finally:
        await session.close()


async def subscribe_conversation_message(
    conversation_id: int,
    message_id: int,
    request: Request,
    context: CopilotContext,
    db: DbSession,
    after: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    service = ConversationService(cast(AsyncSession, db), context)
    snapshot = await service.prepare_subscribe(conversation_id, message_id)
    cursor = after
    if last_event_id and last_event_id.isdigit():
        cursor = max(cursor, int(last_event_id))

    async def event_stream():
        if snapshot.kind != "live":
            yield _sse(snapshot.event_name(), snapshot.to_event() | {"conversation_id": conversation_id}, cursor)
            return
        terminal = False
        async for chunk in iter_message_sse(
            context.tenant_id,
            context.user_id,
            snapshot.message_id,
            cursor,
        ):
            if _sse_chunk_is_terminal(chunk):
                terminal = True
            yield chunk
        if not terminal:
            follow = await _followup_subscribe_snapshot(context, conversation_id, message_id)
            yield _sse(
                follow.event_name(),
                follow.to_event() | {"conversation_id": conversation_id},
                cursor,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{conversation_id}/messages/{message_id}/cancel",
    summary="取消正在执行的 Chat Run",
)
async def cancel_conversation_message(
    conversation_id: int,
    message_id: int,
    context: CopilotContext,
    db: DbSession,
):
    return ok(await ConversationService(cast(AsyncSession, db), context).cancel_message(conversation_id, message_id))


@router.post("/{conversation_id}/messages", summary="发送消息（SSE）")
async def send_conversation_message(
    conversation_id: int,
    payload: ConversationMessageIn,
    request: Request,
    context: CopilotContext,
    workflow: WorkflowDep,
    db: DbSession,
) -> StreamingResponse:
    return await chat_stream(
        ChatRequest(
            conversation_id=conversation_id,
            client_request_id=payload.client_request_id,
            message=payload.message,
            skill_mode=payload.skill_mode,
            skill_key=payload.skill_key,
            retry_of_message_id=payload.retry_of_message_id,
        ),
        request,
        context,
        workflow,
        db,
    )


@router.patch("/{conversation_id}", response_model=ApiResponse[ConversationOut])
async def rename_conversation(
    conversation_id: int, payload: ConversationRename, context: CopilotContext, db: DbSession
):
    return ok(
        await ConversationService(cast(AsyncSession, db), context).rename(
            conversation_id, payload.title
        )
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: int, context: CopilotContext, db: DbSession):
    await ConversationService(cast(AsyncSession, db), context).delete(conversation_id)
    return Response(status_code=204)
