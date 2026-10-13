from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.knowledge import (
    ChunkStatus,
    DocumentChunk,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
)
from app.models.rag import ChunkEmbedding
from app.repositories.knowledge import KnowledgeBaseRepository
from app.schemas.rag import IndexStatusOut
from app.services.authorization import AuthorizationService
from app.services.embedding import enqueue_embed_task

_UNAVAILABLE_BASE = "知识库不存在或不可访问"


class IndexService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()
        self.bases = KnowledgeBaseRepository(session, context.tenant_id)

    async def status(self, knowledge_base_id: int) -> IndexStatusOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        base = await self.bases.get_in_tenant(knowledge_base_id)
        if base is None:
            raise AppError(_UNAVAILABLE_BASE, code=40450, status_code=404)
        tenant_id = self.context.tenant_id
        total = int(
            await self.session.scalar(
                select(func.count(DocumentChunk.id))
                .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
                .where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.knowledge_base_id == knowledge_base_id,
                    DocumentChunk.status == ChunkStatus.ACTIVE.value,
                    DocumentChunk.enabled.is_(True),
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.deleted_at.is_(None),
                    KnowledgeDocument.active_chunk_version == DocumentChunk.version,
                )
            )
            or 0
        )
        rows = (
            await self.session.execute(
                select(ChunkEmbedding.status, func.count())
                .where(
                    ChunkEmbedding.tenant_id == tenant_id,
                    ChunkEmbedding.knowledge_base_id == knowledge_base_id,
                    ChunkEmbedding.model_name == settings.embedding_model,
                    ChunkEmbedding.dimensions == settings.embedding_dimensions,
                )
                .group_by(ChunkEmbedding.status)
            )
        ).all()
        counts = {status: int(count) for status, count in rows}
        return IndexStatusOut(
            knowledge_base_id=knowledge_base_id,
            model_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            total_active_chunks=total,
            ready=counts.get("READY", 0),
            pending=counts.get("PENDING", 0),
            stale=counts.get("STALE", 0),
            failed=counts.get("FAILED", 0),
        )

    async def reindex(self, knowledge_base_id: int) -> int:
        """为知识库下已完成文档排队重建向量。不影响原 Chunk。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        base = await self.bases.get_in_tenant(knowledge_base_id)
        if base is None:
            raise AppError(_UNAVAILABLE_BASE, code=40450, status_code=404)
        docs = list(
            (
                await self.session.scalars(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.tenant_id == self.context.tenant_id,
                        KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                        KnowledgeDocument.deleted_at.is_(None),
                        KnowledgeDocument.status == KnowledgeDocumentStatus.COMPLETED.value,
                    )
                )
            ).all()
        )
        task_ids: list[int] = []
        for document in docs:
            task = await enqueue_embed_task(self.session, document, self.context.user_id)
            if task is not None:
                task_ids.append(task.id)
        await self.session.commit()
        if settings.task_executor != "redis":
            from app.services.processing import ProcessingService

            for task_id in task_ids:
                await ProcessingService(self.session).execute(task_id)
        return len(task_ids)
