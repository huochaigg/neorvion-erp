"""为 ACTIVE 切片生成/更新向量。失败不影响 V2 文档与 Chunk 正文。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_client
from app.core.config import settings
from app.core.exceptions import AppError
from app.models.knowledge import (
    ChunkStatus,
    DocumentChunk,
    DocumentProcessingTask,
    KnowledgeDocument,
    TaskStatus,
    TaskType,
)
from app.models.rag import ChunkEmbedding, EmbeddingStatus
from app.processing.hashing import content_sha256
from app.repositories.documents import TaskRepository, get_live_document
from app.tasks.queue import enqueue_task

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, session: AsyncSession, tenant_id: int | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def execute(self, task: DocumentProcessingTask) -> None:
        """执行文档级 EMBED 任务：只处理当前 ACTIVE 切片。"""
        document = await get_live_document(self.session, task.tenant_id, task.document_id)
        if document is None:
            raise AppError("文档或知识库已删除，任务取消", code=40451, status_code=404)
        chunks = list(
            (
                await self.session.scalars(
                    select(DocumentChunk).where(
                        DocumentChunk.tenant_id == task.tenant_id,
                        DocumentChunk.document_id == document.id,
                        DocumentChunk.status == ChunkStatus.ACTIVE.value,
                        DocumentChunk.version == document.active_chunk_version,
                    )
                )
            ).all()
        )
        await self._delete_other_versions(document)
        if not chunks:
            task.progress = 100
            task.status = TaskStatus.SUCCESS.value
            task.finished_at = datetime.now(UTC)
            await self.session.commit()
            return
        total = len(chunks)
        batch_size = max(1, settings.embedding_batch_size)
        client = get_embedding_client()
        for start in range(0, total, batch_size):
            if await get_live_document(self.session, document.tenant_id, document.id) is None:
                raise AppError("文档或知识库已删除，任务取消", code=40451, status_code=404)
            batch = chunks[start : start + batch_size]
            await self._embed_batch(document, batch, client)
            task.progress = min(99, int((start + len(batch)) / total * 100))
            await self.session.commit()
        task.progress = 100
        task.status = TaskStatus.SUCCESS.value
        task.finished_at = datetime.now(UTC)
        await self.session.commit()

    async def _delete_other_versions(self, document: KnowledgeDocument) -> None:
        rows = list(
            (
                await self.session.scalars(
                    select(ChunkEmbedding).where(
                        ChunkEmbedding.tenant_id == document.tenant_id,
                        ChunkEmbedding.document_id == document.id,
                        ChunkEmbedding.chunk_version != document.active_chunk_version,
                    )
                )
            ).all()
        )
        for row in rows:
            await self.session.delete(row)

    async def _embed_batch(
        self,
        document: KnowledgeDocument,
        chunks: list[DocumentChunk],
        client,
    ) -> None:
        texts = [item.content for item in chunks]
        vectors = await self._embed_with_retry(client, texts)
        now = datetime.now(UTC)
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != settings.embedding_dimensions:
                raise AppError(
                    f"向量维度不一致：期望 {settings.embedding_dimensions}，实际 {len(vector)}",
                    code=40090,
                    status_code=400,
                )
            digest = content_sha256(chunk.content)
            row = await self.session.scalar(
                select(ChunkEmbedding).where(
                    ChunkEmbedding.tenant_id == document.tenant_id,
                    ChunkEmbedding.chunk_id == chunk.id,
                )
            )
            if row is None:
                row = ChunkEmbedding(
                    tenant_id=document.tenant_id,
                    knowledge_base_id=document.knowledge_base_id,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    chunk_version=chunk.version,
                    embedding=vector,
                    model_name=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                    content_hash=digest,
                    status=EmbeddingStatus.READY.value,
                    indexed_at=now,
                    error_message=None,
                )
                self.session.add(row)
            else:
                row.embedding = vector
                row.chunk_version = chunk.version
                row.model_name = settings.embedding_model
                row.dimensions = settings.embedding_dimensions
                row.content_hash = digest
                row.status = EmbeddingStatus.READY.value
                row.indexed_at = now
                row.error_message = None

    async def _embed_with_retry(self, client, texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(settings.embedding_max_retries + 1):
            try:
                return await client.embed(texts)
            except AppError as exc:
                last_error = exc
                if exc.status_code == 429 and attempt < settings.embedding_max_retries:
                    continue
                if exc.status_code >= 500 and attempt < settings.embedding_max_retries:
                    continue
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < settings.embedding_max_retries:
                    continue
                raise AppError("Embedding 调用失败", code=50263, status_code=502) from exc
        raise AppError("Embedding 调用失败", code=50263, status_code=502) from last_error


async def enqueue_embed_task(
    session: AsyncSession,
    document: KnowledgeDocument,
    user_id: int,
) -> DocumentProcessingTask | None:
    """为文档创建 EMBED 任务。已有进行中任务则跳过。已删除文档不再入队。"""
    if await get_live_document(session, document.tenant_id, document.id) is None:
        return None
    tasks = TaskRepository(session, document.tenant_id)
    existed = await tasks.find_active(document.id, TaskType.EMBED.value)
    if existed is not None:
        return None
    task = DocumentProcessingTask(
        tenant_id=document.tenant_id,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        task_type=TaskType.EMBED.value,
        status=TaskStatus.QUEUED.value,
        payload={"model": settings.embedding_model, "dimensions": settings.embedding_dimensions},
        created_by=user_id,
    )
    session.add(task)
    await session.flush()
    if settings.task_executor == "redis":
        await enqueue_task(task.id)
    return task
