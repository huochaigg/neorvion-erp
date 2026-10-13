from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession, KnowledgeReadContext
from app.models.rag import Conversation, Message
from app.schemas.common import ApiResponse, ok
from app.schemas.rag import (
    ChatAskIn,
    CitationOut,
    ConversationCreateIn,
    ConversationDetailOut,
    ConversationListOut,
    ConversationOut,
    MessageOut,
)
from app.services.chat import ChatService

router = APIRouter(tags=["knowledge-chat"])


def _conversation_out(row: Conversation) -> ConversationOut:
    return ConversationOut(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        knowledge_base_ids=list(row.knowledge_base_ids or []),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_out(row: Message, citations: list | None = None) -> MessageOut:
    return MessageOut(
        id=row.id,
        conversation_id=row.conversation_id,
        role=row.role,
        content=row.content,
        status=row.status,
        retrieval_strategy=row.retrieval_strategy,
        usage=row.usage,
        latency_ms=row.latency_ms,
        error_message=row.error_message,
        created_at=row.created_at,
        citations=[
            CitationOut(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                knowledge_base_id=item.knowledge_base_id,
                filename=item.filename,
                page_no=item.page_no,
                heading=item.heading,
                snippet=item.snippet,
                rank=item.rank,
                vector_score=item.vector_score,
                keyword_score=item.keyword_score,
                rrf_score=item.rrf_score,
                rerank_score=item.rerank_score,
            )
            for item in citations or []
        ],
    )


@router.post("/conversations", response_model=ApiResponse[ConversationOut], summary="创建问答会话")
async def create_conversation(
    payload: ConversationCreateIn,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[ConversationOut]:
    row = await ChatService(session, context).create_conversation(payload.title, payload.knowledge_base_ids)
    return ok(_conversation_out(row), "已创建会话")


@router.get("/conversations", response_model=ApiResponse[ConversationListOut], summary="会话列表")
async def list_conversations(
    context: KnowledgeReadContext,
    session: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[ConversationListOut]:
    items, total = await ChatService(session, context).list_conversations(page, page_size)
    return ok(
        ConversationListOut(
            items=[_conversation_out(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/conversations/{conversation_id}", response_model=ApiResponse[ConversationDetailOut], summary="会话详情")
async def get_conversation(
    conversation_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[ConversationDetailOut]:
    service = ChatService(session, context)
    row = await service.get_conversation(conversation_id)
    messages = await service.conversations.list_messages(row.id)
    out_messages = []
    for message in messages:
        citations = await service.conversations.list_citations(message.id)
        out_messages.append(_message_out(message, citations))
    base = _conversation_out(row)
    return ok(ConversationDetailOut(**base.model_dump(), messages=out_messages))


@router.delete("/conversations/{conversation_id}", response_model=ApiResponse[None], summary="删除会话")
async def delete_conversation(
    conversation_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[None]:
    await ChatService(session, context).delete_conversation(conversation_id)
    return ok(None, "已删除")


@router.post("/conversations/{conversation_id}/messages", summary="发送问题（SSE）")
async def ask(
    conversation_id: int,
    payload: ChatAskIn,
    request: Request,
    context: KnowledgeReadContext,
    session: DbSession,
) -> StreamingResponse:
    service = ChatService(session, context)

    async def event_stream():
        async for chunk in service.stream_answer(
            conversation_id,
            payload.content,
            strategy=payload.strategy,
            top_k=payload.top_k,
            rerank=payload.rerank,
            disconnected=request.is_disconnected,
            regenerate_of=payload.regenerate_of,
        ):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
