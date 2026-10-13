"""向量、会话与检索日志仓储。查询一律带 tenant_id。"""

from __future__ import annotations

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import (
    ChunkEmbedding,
    Conversation,
    EmbeddingStatus,
    Message,
    MessageCitation,
    ModelProfile,
)
from app.repositories.base import BaseRepository


class EmbeddingRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int | None = None) -> None:
        super().__init__(session, tenant_id)

    async def get_for_chunk(self, chunk_id: int) -> ChunkEmbedding | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(ChunkEmbedding).where(
                ChunkEmbedding.tenant_id == tenant_id,
                ChunkEmbedding.chunk_id == chunk_id,
            )
        )

    async def list_pending_for_document(self, document_id: int) -> list[ChunkEmbedding]:
        tenant_id = self.ensure_tenant()
        stmt = select(ChunkEmbedding).where(
            ChunkEmbedding.tenant_id == tenant_id,
            ChunkEmbedding.document_id == document_id,
            ChunkEmbedding.status.in_(
                (EmbeddingStatus.PENDING.value, EmbeddingStatus.STALE.value, EmbeddingStatus.FAILED.value)
            ),
        )
        return list((await self.session.scalars(stmt)).all())

    async def delete_for_document_except_version(self, document_id: int, version: int) -> None:
        tenant_id = self.ensure_tenant()
        await self.session.execute(
            delete(ChunkEmbedding).where(
                ChunkEmbedding.tenant_id == tenant_id,
                ChunkEmbedding.document_id == document_id,
                ChunkEmbedding.chunk_version != version,
            )
        )

    async def mark_stale(self, chunk_id: int) -> None:
        tenant_id = self.ensure_tenant()
        await self.session.execute(
            update(ChunkEmbedding)
            .where(ChunkEmbedding.tenant_id == tenant_id, ChunkEmbedding.chunk_id == chunk_id)
            .values(status=EmbeddingStatus.STALE.value)
        )

    async def counts_for_base(self, knowledge_base_id: int, *, model_name: str, dimensions: int) -> dict[str, int]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(ChunkEmbedding.status, func.count())
            .where(
                ChunkEmbedding.tenant_id == tenant_id,
                ChunkEmbedding.knowledge_base_id == knowledge_base_id,
                ChunkEmbedding.model_name == model_name,
                ChunkEmbedding.dimensions == dimensions,
            )
            .group_by(ChunkEmbedding.status)
        )
        rows = (await self.session.execute(stmt)).all()
        data = {status: int(count) for status, count in rows}
        return data


class ConversationRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int | None = None) -> None:
        super().__init__(session, tenant_id)

    def _owned(self) -> Select[tuple[Conversation]]:
        tenant_id = self.ensure_tenant()
        return select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.deleted_at.is_(None),
        )

    async def list_page(self, *, user_id: int, page: int, page_size: int) -> tuple[list[Conversation], int]:
        filters = self._owned().where(Conversation.created_by == user_id)
        total = int(await self.session.scalar(select(func.count()).select_from(filters.subquery())) or 0)
        stmt = filters.order_by(Conversation.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
        return list((await self.session.scalars(stmt)).all()), total

    async def get_owned(self, conversation_id: int, user_id: int) -> Conversation | None:
        stmt = self._owned().where(Conversation.id == conversation_id, Conversation.created_by == user_id)
        return await self.session.scalar(stmt)

    async def list_messages(self, conversation_id: int) -> list[Message]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Message)
            .where(Message.tenant_id == tenant_id, Message.conversation_id == conversation_id)
            .order_by(Message.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_citations(self, message_id: int) -> list[MessageCitation]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(MessageCitation)
            .where(MessageCitation.tenant_id == tenant_id, MessageCitation.message_id == message_id)
            .order_by(MessageCitation.rank.asc())
        )
        return list((await self.session.scalars(stmt)).all())


class ModelProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[ModelProfile]:
        stmt = select(ModelProfile).order_by(ModelProfile.kind, ModelProfile.id)
        return list((await self.session.scalars(stmt)).all())

    async def get(self, profile_id: int) -> ModelProfile | None:
        return await self.session.get(ModelProfile, profile_id)


class RetrievalLogRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int | None = None) -> None:
        super().__init__(session, tenant_id)
