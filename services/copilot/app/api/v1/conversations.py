from typing import cast

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CopilotContext, DbSession, WorkflowDep
from app.api.v1.chat import chat_stream
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


@router.get("/{conversation_id}", response_model=ApiResponse[ConversationDetailOut], summary="加载会话详情")
async def get_conversation(conversation_id: int, request: Request, context: CopilotContext, db: DbSession):
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
        ),
        request,
        context,
        workflow,
        db,
    )


@router.patch("/{conversation_id}", response_model=ApiResponse[ConversationOut])
async def rename_conversation(conversation_id: int, payload: ConversationRename, context: CopilotContext, db: DbSession):
    return ok(await ConversationService(cast(AsyncSession, db), context).rename(conversation_id, payload.title))


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: int, context: CopilotContext, db: DbSession):
    await ConversationService(cast(AsyncSession, db), context).delete(conversation_id)
    return Response(status_code=204)
