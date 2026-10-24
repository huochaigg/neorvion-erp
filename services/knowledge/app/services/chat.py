"""知识问答。LLM 调用期间不持有数据库事务。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.ai.factory import get_chat_client
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.knowledge import KnowledgeBase
from app.models.rag import (
    Conversation,
    Message,
    MessageCitation,
    MessageRole,
    MessageStatus,
)
from app.repositories.rag import ConversationRepository
from app.evaluation.prompt import SYSTEM_PROMPT, build_rag_messages
from app.services.retrieval import RetrievalService, RetrievedHit

_REFUSE = "知识库中没有足够依据回答该问题。我不会把缺少证据的猜测当成事实。"
_SYSTEM = SYSTEM_PROMPT


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.conversations = ConversationRepository(session, context.tenant_id)

    async def create_conversation(self, title: str | None, knowledge_base_ids: list[int] | None) -> Conversation:
        bases = await RetrievalService(self.session, self.context)._authorized_base_ids(knowledge_base_ids)
        row = Conversation(
            tenant_id=self.context.tenant_id,
            title=(title or "新对话").strip() or "新对话",
            knowledge_base_ids=bases,
            created_by=self.context.user_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list_conversations(self, page: int, page_size: int):
        return await self.conversations.list_page(user_id=self.context.user_id, page=page, page_size=page_size)

    async def get_conversation(self, conversation_id: int) -> Conversation:
        row = await self.conversations.get_owned(conversation_id, self.context.user_id)
        if row is None:
            raise AppError("会话不存在或不可访问", code=40470, status_code=404)
        return row

    async def delete_conversation(self, conversation_id: int) -> None:
        row = await self.get_conversation(conversation_id)
        row.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def update_conversation(
        self,
        conversation_id: int,
        *,
        title: str | None,
        knowledge_base_ids: list[int] | None,
    ) -> Conversation:
        row = await self.get_conversation(conversation_id)
        if title is not None:
            row.title = title.strip() or row.title
        if knowledge_base_ids is not None:
            bases = await RetrievalService(self.session, self.context)._authorized_base_ids(
                knowledge_base_ids or None
            )
            row.knowledge_base_ids = bases
            flag_modified(row, "knowledge_base_ids")
        row.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def stream_answer(
        self,
        conversation_id: int,
        question: str,
        *,
        strategy: str,
        top_k: int | None,
        rerank: bool,
        disconnected,
        regenerate_of: int | None = None,
    ) -> AsyncIterator[str]:
        """产出 SSE 文本。调用方不要在流式期间占用外层事务。"""
        try:
            conversation = await self.get_conversation(conversation_id)
        except AppError as exc:
            yield _sse("error", {"message": exc.message, "code": exc.code})
            return
        question_text = question.strip()
        if regenerate_of is not None:
            original = await self.session.get(Message, regenerate_of)
            if (
                original is None
                or original.tenant_id != self.context.tenant_id
                or original.conversation_id != conversation.id
                or original.role != MessageRole.ASSISTANT.value
            ):
                yield _sse("error", {"message": "原回答不存在或不可重新生成", "code": 40472})
                return
            history_rows = await self.conversations.list_messages(conversation.id)
            prior_user = next(
                (
                    item
                    for item in reversed(history_rows)
                    if item.id < original.id and item.role == MessageRole.USER.value
                ),
                None,
            )
            if prior_user is not None:
                question_text = prior_user.content.strip()
        else:
            self.session.add(
                Message(
                    tenant_id=self.context.tenant_id,
                    conversation_id=conversation.id,
                    role=MessageRole.USER.value,
                    content=question_text,
                    status=MessageStatus.COMPLETED.value,
                    created_by=self.context.user_id,
                )
            )
        assistant = Message(
            tenant_id=self.context.tenant_id,
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT.value,
            content="",
            status=MessageStatus.STREAMING.value,
            retrieval_strategy=strategy,
            created_by=self.context.user_id,
        )
        self.session.add(assistant)
        conversation.updated_at = datetime.now(UTC)
        if conversation.title == "新对话":
            conversation.title = question_text[:40]
        await self.session.commit()
        await self.session.refresh(assistant)
        yield _sse("status", {"stage": "retrieving", "message_id": assistant.id})

        retrieval = RetrievalService(self.session, self.context)
        started = datetime.now(UTC)
        try:
            result = await retrieval.search(
                question_text,
                knowledge_base_ids=list(conversation.knowledge_base_ids or []),
                strategy=strategy,
                top_k=top_k,
                rerank=rerank,
                persist_log=True,
                conversation_id=conversation.id,
                message_id=assistant.id,
            )
        except AppError as exc:
            await self._fail_assistant(assistant.id, exc.message)
            yield _sse("error", {"message": exc.message, "code": exc.code})
            return

        for hit in result.hits:
            yield _sse(
                "citation",
                {
                    "chunk_id": hit.chunk_id,
                    "document_id": hit.document_id,
                    "knowledge_base_id": hit.knowledge_base_id,
                    "filename": hit.filename,
                    "page_no": hit.page_no,
                    "heading": hit.heading,
                    "snippet": hit.content[:400],
                    "rank": hit.final_rank,
                    "vector_score": hit.vector_score,
                    "keyword_score": hit.keyword_score,
                    "rrf_score": hit.rrf_score,
                    "rerank_score": hit.rerank_score,
                },
            )

        if not result.hits:
            refuse = await self._refuse_text(result.knowledge_base_ids)
            await self._complete_assistant(assistant.id, refuse, [], result.strategy, None, 0)
            yield _sse("token", {"text": refuse})
            yield _sse("done", {"message_id": assistant.id, "usage": None})
            return

        yield _sse("status", {"stage": "generating", "message_id": assistant.id})
        history = await self._history_messages(conversation.id, exclude_id=assistant.id)
        prompt = self._build_messages(question_text, result.hits, history).messages
        chunks: list[str] = []
        usage = None
        try:
            client = get_chat_client()
            async for delta in client.stream(prompt):
                if await disconnected():
                    await self._cancel_assistant(assistant.id, "".join(chunks))
                    yield _sse("error", {"message": "生成已取消", "code": 49901})
                    return
                if delta.text:
                    chunks.append(delta.text)
                    yield _sse("token", {"text": delta.text})
                if delta.finished:
                    usage = {
                        "prompt_tokens": delta.prompt_tokens,
                        "completion_tokens": delta.completion_tokens,
                    }
        except AppError as exc:
            await self._fail_assistant(assistant.id, exc.message)
            yield _sse("error", {"message": exc.message, "code": exc.code})
            return
        except Exception:
            await self._fail_assistant(assistant.id, "生成失败")
            yield _sse("error", {"message": "生成失败", "code": 50264})
            return

        latency = int((datetime.now(UTC) - started).total_seconds() * 1000)
        answer = "".join(chunks).strip() or _REFUSE
        await self._complete_assistant(assistant.id, answer, result.hits, result.strategy, usage, latency)
        yield _sse("done", {"message_id": assistant.id, "usage": usage, "latency_ms": latency})

    async def _refuse_text(self, knowledge_base_ids: list[int]) -> str:
        if not knowledge_base_ids:
            return _REFUSE
        rows = (
            await self.session.execute(
                select(KnowledgeBase.id, KnowledgeBase.name).where(
                    KnowledgeBase.tenant_id == self.context.tenant_id,
                    KnowledgeBase.id.in_(knowledge_base_ids),
                    KnowledgeBase.deleted_at.is_(None),
                )
            )
        ).all()
        names = {int(row.id): str(row.name) for row in rows}
        ordered = [names[item] for item in knowledge_base_ids if item in names]
        if not ordered:
            return _REFUSE
        return (
            f"{_REFUSE}\n当前会话检索范围：{'、'.join(ordered)}。"
            "若答案在其他知识库，请在问答页更换本会话绑定的知识库后再问。"
        )

    async def _history_messages(self, conversation_id: int, *, exclude_id: int) -> list[Message]:
        rows = await self.conversations.list_messages(conversation_id)
        usable = [
            item
            for item in rows
            if item.id != exclude_id and item.status == MessageStatus.COMPLETED.value
        ]
        keep = settings.chat_history_turns * 2
        return usable[-keep:]

    def _build_messages(
        self,
        question: str,
        hits: list[RetrievedHit],
        history: list[Message],
    ):
        return build_rag_messages(
            question,
            hits,
            history,
            budget=settings.chat_max_context_chars,
        )

    async def _complete_assistant(
        self,
        message_id: int,
        content: str,
        hits: list[RetrievedHit],
        strategy: str,
        usage: dict | None,
        latency_ms: int,
    ) -> None:
        """流式生成结束后落库：补全 assistant 正文，并写入本次检索引用。"""
        row = await self.session.get(Message, message_id)
        # 消息不存在或不属于当前租户时直接放弃，避免串写
        if row is None or row.tenant_id != self.context.tenant_id:
            return
        # 开始时 content 为空、status=STREAMING；这里改成完整答案并标记完成
        row.content = content
        row.status = MessageStatus.COMPLETED.value
        row.retrieval_strategy = strategy
        row.usage = usage
        row.latency_ms = latency_ms
        # usage 是 JSON 字段，原地改 dict 时需显式标记，否则 SQLAlchemy 可能不更新
        if usage is not None:
            flag_modified(row, "usage")
        # 每条命中存一条引用：chunk_id 对正文，rank 对前端展示序号 / prompt 里的 [n]
        for hit in hits:
            self.session.add(
                MessageCitation(
                    tenant_id=self.context.tenant_id,
                    message_id=row.id,
                    knowledge_base_id=hit.knowledge_base_id,
                    document_id=hit.document_id,
                    chunk_id=hit.chunk_id,
                    filename=hit.filename,
                    page_no=hit.page_no,
                    heading=hit.heading,
                    snippet=hit.content[:500],
                    rank=hit.final_rank,
                    vector_score=hit.vector_score,
                    keyword_score=hit.keyword_score,
                    rrf_score=hit.rrf_score,
                    rerank_score=hit.rerank_score,
                )
            )
        await self.session.commit()

    async def _fail_assistant(self, message_id: int, message: str) -> None:
        row = await self.session.get(Message, message_id)
        if row is None or row.tenant_id != self.context.tenant_id:
            return
        row.status = MessageStatus.FAILED.value
        row.error_message = message
        await self.session.commit()

    async def _cancel_assistant(self, message_id: int, content: str) -> None:
        row = await self.session.get(Message, message_id)
        if row is None or row.tenant_id != self.context.tenant_id:
            return
        row.status = MessageStatus.CANCELLED.value
        row.content = content
        await self.session.commit()
