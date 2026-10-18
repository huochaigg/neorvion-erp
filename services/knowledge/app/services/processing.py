"""解析与切片执行器。任务状态落库；失败时保留旧 ACTIVE Chunk。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.knowledge import (
    ChunkStatus,
    DocumentChunk,
    DocumentProcessingTask,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    TaskStatus,
    TaskType,
)
from app.processing.extract import extract_document
from app.processing.split import split_text, validate_chunk_params
from app.processing.storage import read_bytes
from app.repositories.documents import ChunkRepository, TaskRepository, get_live_document

logger = logging.getLogger(__name__)


class ProcessingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute(self, task_id: int) -> None:
        """领取并执行一条任务。可被 Worker 或测试内联调用。"""
        task = await self.session.scalar(
            select(DocumentProcessingTask).where(DocumentProcessingTask.id == task_id).with_for_update()
        )
        if task is None:
            return
        if task.status not in {TaskStatus.QUEUED.value, TaskStatus.RUNNING.value}:
            """TODO 这里需要考虑是否需要RUNNING状态，同时判断两个状态可能会遇到问题，后续调整可能会调整多个地方，改为只判断QUEUED状态"""
            return
        task.status = TaskStatus.RUNNING.value
        task.progress = 5
        task.started_at = datetime.now(UTC)
        task.error_message = None
        document = await get_live_document(self.session, task.tenant_id, task.document_id)
        if document is None:
            task.status = TaskStatus.FAILED.value
            task.error_message = "文档或知识库已删除，任务取消"
            task.finished_at = datetime.now(UTC)
            await self.session.commit()
            return
        if task.task_type != TaskType.EMBED.value:
            document.status = KnowledgeDocumentStatus.PROCESSING.value
            document.updated_by = task.created_by
        await self.session.commit()
        try:
            if task.task_type == TaskType.PARSE.value:
                await self._parse(task, document)
            elif task.task_type == TaskType.CHUNK.value:
                await self._chunk(task, document)
            elif task.task_type == TaskType.EMBED.value:
                from app.services.embedding import EmbeddingService

                await EmbeddingService(self.session, document.tenant_id).execute(task)
            else:
                raise AppError("未知任务类型", code=40078, status_code=400)
        except AppError as exc:
            await self._fail(task.id, document.id, exc.message, fail_document=task.task_type != TaskType.EMBED.value)
        except Exception:
            logger.exception("knowledge task failed id=%s", task_id)
            await self._fail(
                task.id,
                document.id,
                "处理失败，请查看任务详情后重试",
                fail_document=task.task_type != TaskType.EMBED.value,
            )

    async def _parse(self, task: DocumentProcessingTask, document: KnowledgeDocument) -> None:
        task.progress = 20
        await self.session.commit()
        payload = read_bytes(document.storage_key)
        result = extract_document(document.filename, payload)
        document.extracted_text = result.text
        document.extract_meta = {
            "parser": result.parser,
            "headings": result.headings,
            "pages": [{"page_no": page.page_no, "text": page.text, "heading": page.heading} for page in result.pages],
        }
        flag_modified(document, "extract_meta")
        document.warning_message = result.warning
        document.error_message = None
        task.progress = 70
        await self.session.commit()
        if await get_live_document(self.session, document.tenant_id, document.id) is None:
            raise AppError("文档或知识库已删除，任务取消", code=40970, status_code=409)
        chunk_task = await self._enqueue_followup_chunk(document, task.created_by)
        document.status = KnowledgeDocumentStatus.PROCESSING.value
        task.status = TaskStatus.SUCCESS.value
        task.progress = 100
        task.finished_at = datetime.now(UTC)
        await self.session.commit()
        if chunk_task is not None and settings.task_executor != "redis":
            await ProcessingService(self.session).execute(chunk_task.id)

    async def _enqueue_followup_chunk(
        self,
        document: KnowledgeDocument,
        user_id: int,
    ) -> DocumentProcessingTask | None:
        tasks = TaskRepository(self.session, document.tenant_id)
        existed = await tasks.find_active(document.id, TaskType.CHUNK.value)
        if existed is not None:
            return None
        payload = {
            "strategy": document.chunk_strategy or "RECURSIVE",
            "chunk_size": document.chunk_size or settings.default_chunk_size,
            "chunk_overlap": document.chunk_overlap or settings.default_chunk_overlap,
        }
        task = DocumentProcessingTask(
            tenant_id=document.tenant_id,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            task_type=TaskType.CHUNK.value,
            status=TaskStatus.QUEUED.value,
            payload=payload,
            created_by=user_id,
        )
        self.session.add(task)
        await self.session.flush()
        if settings.task_executor == "redis":
            from app.tasks.queue import enqueue_task

            await enqueue_task(task.id)
        return task

    async def _chunk(self, task: DocumentProcessingTask, document: KnowledgeDocument) -> None:
        if not (document.extracted_text or "").strip():
            raise AppError("没有可切片的文本，请先成功解析", code=40077, status_code=400)
        payload = task.payload or {}
        strategy, chunk_size, chunk_overlap = validate_chunk_params(
            str(payload.get("strategy") or document.chunk_strategy or "RECURSIVE"),
            int(payload.get("chunk_size") or document.chunk_size or settings.default_chunk_size),
            int(payload.get("chunk_overlap") or document.chunk_overlap or settings.default_chunk_overlap),
        )
        task.progress = 30
        await self.session.commit()
        pages = []
        if isinstance(document.extract_meta, dict):
            raw_pages = document.extract_meta.get("pages") or []
            if isinstance(raw_pages, list):
                pages = [item for item in raw_pages if isinstance(item, dict)]
            headings = document.extract_meta.get("headings") if isinstance(document.extract_meta.get("headings"), list) else []
        else:
            headings = []
        drafts = split_text(
            document.extracted_text or "",
            strategy=strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            pages=pages,
            headings=[str(item) for item in headings] if headings else None,
        )
        next_version = int(document.active_chunk_version or 0) + 1
        chunks = ChunkRepository(self.session, document.tenant_id)
        if await get_live_document(self.session, document.tenant_id, document.id) is None:
            raise AppError("文档或知识库已删除，任务取消", code=40970, status_code=409)
        await chunks.delete_version(document.id, next_version)
        for draft in drafts:
            self.session.add(
                DocumentChunk(
                    tenant_id=document.tenant_id,
                    knowledge_base_id=document.knowledge_base_id,
                    document_id=document.id,
                    version=next_version,
                    chunk_index=draft.index,
                    content=draft.content,
                    char_count=draft.char_count,
                    page_no=draft.page_no,
                    heading=draft.heading,
                    source_start=draft.source_start,
                    source_end=draft.source_end,
                    extra={"unit": "char"},
                    status=ChunkStatus.DRAFT.value,
                    enabled=True,
                    updated_by=task.created_by,
                )
            )
        await self.session.flush()
        if await get_live_document(self.session, document.tenant_id, document.id) is None:
            await chunks.delete_version(document.id, next_version)
            raise AppError("文档或知识库已删除，任务取消", code=40970, status_code=409)
        await chunks.supersede_active(document.id)
        rows = list(
            (
                await self.session.scalars(
                    select(DocumentChunk).where(
                        DocumentChunk.tenant_id == document.tenant_id,
                        DocumentChunk.document_id == document.id,
                        DocumentChunk.version == next_version,
                    )
                )
            ).all()
        )
        for row in rows:
            row.status = ChunkStatus.ACTIVE.value
        document.active_chunk_version = next_version
        document.chunk_strategy = strategy
        document.chunk_size = chunk_size
        document.chunk_overlap = chunk_overlap
        document.chunk_unit = "char"
        document.status = KnowledgeDocumentStatus.COMPLETED.value
        document.error_message = None
        document.updated_by = task.created_by
        task.status = TaskStatus.SUCCESS.value
        task.progress = 100
        task.finished_at = datetime.now(UTC)
        await self.session.commit()
        if await get_live_document(self.session, document.tenant_id, document.id) is None:
            return
        embed_task = await self._enqueue_followup_embed(document, task.created_by)
        if embed_task is not None and settings.task_executor != "redis":
            await ProcessingService(self.session).execute(embed_task.id)

    async def _enqueue_followup_embed(self, document: KnowledgeDocument, user_id: int) -> DocumentProcessingTask | None:
        from app.services.embedding import enqueue_embed_task

        return await enqueue_embed_task(self.session, document, user_id)

    async def _fail(
        self,
        task_id: int,
        document_id: int,
        message: str,
        *,
        fail_document: bool = True,
    ) -> None:
        await self.session.rollback()
        task = await self.session.get(DocumentProcessingTask, task_id)
        document = await self.session.get(KnowledgeDocument, document_id)
        if task is not None:
            task.status = TaskStatus.FAILED.value
            task.error_message = message
            task.finished_at = datetime.now(UTC)
            task.progress = min(task.progress or 0, 90)
        if fail_document and document is not None:
            document.status = KnowledgeDocumentStatus.FAILED.value
            document.error_message = message
        await self.session.commit()
