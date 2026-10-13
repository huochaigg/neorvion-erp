"""文档上传、下载、删除、任务调度与工作台统计。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.knowledge import (
    DocumentProcessingTask,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    TaskStatus,
    TaskType,
)
from app.processing.extract import sniff_kind
from app.processing.split import validate_chunk_params
from app.processing.storage import (
    build_storage_key,
    delete_document_files,
    ensure_allowed_extension,
    resolve_stored_path,
    sanitize_filename,
    sha256_bytes,
    write_bytes,
)
from app.repositories.documents import ChunkRepository, DocumentRepository, TaskRepository
from app.repositories.knowledge import KnowledgeBaseRepository
from app.schemas.documents import (
    ChunkListOut,
    ChunkOut,
    ChunkParamsIn,
    ChunkUpdateIn,
    DocumentDetailOut,
    DocumentListOut,
    DocumentOut,
    OverviewOut,
    TaskListOut,
    TaskOut,
    UploadBatchOut,
    UploadItemOut,
)
from app.services.authorization import AuthorizationService
from app.services.processing import ProcessingService
from app.tasks.queue import enqueue_task

_UNAVAILABLE_BASE = "知识库不存在或不可访问"
_UNAVAILABLE_DOC = "文档不存在或不可访问"
_UNAVAILABLE_CHUNK = "切片不存在或不可访问"
_UNAVAILABLE_TASK = "任务不存在或不可访问"
_PREVIEW_LIMIT = 4000
_ALLOWED_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
}


class DocumentService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()
        self.bases = KnowledgeBaseRepository(session, context.tenant_id)
        self.documents = DocumentRepository(session, context.tenant_id)
        self.chunks = ChunkRepository(session, context.tenant_id)
        self.tasks = TaskRepository(session, context.tenant_id)

    async def overview(self) -> OverviewOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        _, base_total = await self.bases.list_page(q=None, status=None, page=1, page_size=1)
        _, doc_total = await self.documents.list_page(
            knowledge_base_id=None, q=None, status=None, page=1, page_size=1
        )
        status_counts = await self.documents.count_by_status()
        recent = await self.documents.list_recent()
        pending_tasks = await self.tasks.list_pending(limit=8)
        return OverviewOut(
            knowledge_base_count=base_total,
            document_count=doc_total,
            chunk_count=await self.chunks.count_active(),
            document_completed=status_counts.get(KnowledgeDocumentStatus.COMPLETED.value, 0),
            document_failed=status_counts.get(KnowledgeDocumentStatus.FAILED.value, 0),
            pending_task_count=await self.tasks.count_by_status(
                (TaskStatus.QUEUED.value, TaskStatus.RUNNING.value)
            ),
            failed_task_count=await self.tasks.count_by_status((TaskStatus.FAILED.value,)),
            recent_documents=[self._document_out(item) for item in recent],
            pending_tasks=[self._task_out(item) for item in pending_tasks],
        )

    async def list_documents(
        self,
        *,
        knowledge_base_id: int | None,
        q: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> DocumentListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        if knowledge_base_id is not None:
            await self._require_base(knowledge_base_id)
        rows, total = await self.documents.list_page(
            knowledge_base_id=knowledge_base_id,
            q=(q or "").strip() or None,
            status=status,
            page=page,
            page_size=page_size,
        )
        return DocumentListOut(
            items=[self._document_out(item) for item in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_document(self, document_id: int) -> DocumentDetailOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        row = await self._require_document(document_id)
        preview = row.extracted_text[:_PREVIEW_LIMIT] if row.extracted_text else None
        return DocumentDetailOut(
            **self._document_out(row).model_dump(),
            extracted_preview=preview,
            extract_meta=row.extract_meta,
        )

    async def upload(self, knowledge_base_id: int, files: list[UploadFile]) -> UploadBatchOut:
        """批量上传。部分失败不影响已成功写入的文件。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_CREATE,))
        await self._require_base(knowledge_base_id)
        if not files:
            raise AppError("请选择要上传的文件", code=40079, status_code=400)
        if len(files) > settings.max_upload_files:
            raise AppError(f"单次最多上传 {settings.max_upload_files} 个文件", code=40079, status_code=400)
        items: list[UploadItemOut] = []
        follow_up: list[int] = []
        for upload in files:
            filename = sanitize_filename(upload.filename or "unnamed")
            try:
                document, task_id = await self._save_one(knowledge_base_id, upload, filename)
                items.append(
                    UploadItemOut(filename=filename, ok=True, message="已上传并排队解析", document=self._document_out(document))
                )
                if task_id is not None:
                    follow_up.append(task_id)
            except AppError as exc:
                items.append(UploadItemOut(filename=filename, ok=False, message=exc.message, document=None))
        for task_id in follow_up:
            await self._dispatch(task_id)
        return UploadBatchOut(
            items=items,
            succeeded=sum(1 for item in items if item.ok),
            failed=sum(1 for item in items if not item.ok),
        )

    async def _save_one(
        self,
        knowledge_base_id: int,
        upload: UploadFile,
        filename: str,
    ) -> tuple[KnowledgeDocument, int | None]:
        ext = ensure_allowed_extension(filename)
        payload = await upload.read()
        if not payload:
            raise AppError("文件为空", code=40080, status_code=400)
        if len(payload) > settings.max_upload_bytes:
            raise AppError("单个文件不能超过 20MB", code=40080, status_code=400)
        sniff_kind(filename, payload)
        digest = sha256_bytes(payload)
        existed = await self.documents.get_by_sha256(knowledge_base_id, digest)
        if existed is not None:
            raise AppError("相同内容的文件已存在，已按 SHA256 去重", code=40951, status_code=409)
        row = KnowledgeDocument(
            tenant_id=self.context.tenant_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            storage_key="pending",
            file_size=len(payload),
            mime_type=_ALLOWED_MIME.get(ext, upload.content_type or "application/octet-stream"),
            extension=ext,
            sha256=digest,
            status=KnowledgeDocumentStatus.PENDING.value,
            chunk_strategy="RECURSIVE",
            chunk_size=settings.default_chunk_size,
            chunk_overlap=settings.default_chunk_overlap,
            chunk_unit="char",
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.documents.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("相同内容的文件已存在，已按 SHA256 去重", code=40951, status_code=409) from exc
        row.storage_key = build_storage_key(self.context.tenant_id, knowledge_base_id, row.id, ext)
        write_bytes(row.storage_key, payload)
        task = await self._create_task(row, TaskType.PARSE.value, payload=None)
        try:
            await self.session.commit()
        except Exception:
            delete_document_files(self.context.tenant_id, knowledge_base_id, row.id)
            await self.session.rollback()
            raise
        await self.session.refresh(row)
        return row, task.id

    async def stored_path(self, document_id: int):
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        row = await self._require_document(document_id)
        return row.filename, row.mime_type, resolve_stored_path(row.storage_key)

    async def delete_document(self, document_id: int) -> None:
        """软删除文档，清理磁盘文件、切片；任务记录保留便于审计。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self._require_document(document_id)
        active = None
        for task_type in (TaskType.PARSE.value, TaskType.CHUNK.value, TaskType.EMBED.value):
            found = await self.tasks.find_active(row.id, task_type)
            if found is not None:
                found.status = TaskStatus.FAILED.value
                found.error_message = "文档已删除，任务取消"
                found.finished_at = datetime.now(UTC)
                active = found
        await self.chunks.delete_all_for_document(row.id)
        row.deleted_at = datetime.now(UTC)
        row.updated_by = self.context.user_id
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        delete_document_files(row.tenant_id, row.knowledge_base_id, row.id)
        _ = active

    async def request_parse(self, document_id: int) -> TaskOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._require_document(document_id)
        task = await self._create_task(row, TaskType.PARSE.value, payload=None)
        row.status = KnowledgeDocumentStatus.PENDING.value
        await self.session.commit()
        await self._dispatch(task.id)
        await self.session.refresh(task)
        return self._task_out(task)

    async def request_chunk(self, document_id: int, params: ChunkParamsIn) -> TaskOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._require_document(document_id)
        if not (row.extracted_text or "").strip():
            raise AppError("请先成功解析文档再切片", code=40077, status_code=400)
        strategy, chunk_size, overlap = validate_chunk_params(
            params.strategy, params.chunk_size, params.chunk_overlap
        )
        payload = {"strategy": strategy, "chunk_size": chunk_size, "chunk_overlap": overlap}
        task = await self._create_task(row, TaskType.CHUNK.value, payload=payload)
        row.status = KnowledgeDocumentStatus.PROCESSING.value
        await self.session.commit()
        await self._dispatch(task.id)
        await self.session.refresh(task)
        return self._task_out(task)

    async def list_chunks(
        self,
        *,
        knowledge_base_id: int | None,
        document_id: int | None,
        enabled: bool | None,
        page: int,
        page_size: int,
    ) -> ChunkListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        if document_id is not None:
            await self._require_document(document_id)
        if knowledge_base_id is not None:
            await self._require_base(knowledge_base_id)
        rows, total = await self.chunks.list_active(
            document_id=document_id,
            knowledge_base_id=knowledge_base_id,
            enabled=enabled,
            page=page,
            page_size=page_size,
        )
        return ChunkListOut(
            items=[self._chunk_out(item) for item in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_chunk(self, chunk_id: int) -> ChunkOut:
        """按租户读取单条切片，供问答引用查看原文。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        row = await self.chunks.get_in_tenant(chunk_id)
        if row is None or row.status != "ACTIVE":
            raise AppError(_UNAVAILABLE_CHUNK, code=40453, status_code=404)
        return self._chunk_out(row)

    async def update_chunk(self, chunk_id: int, payload: ChunkUpdateIn) -> ChunkOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self.chunks.get_in_tenant(chunk_id)
        if row is None or row.status != "ACTIVE":
            raise AppError(_UNAVAILABLE_CHUNK, code=40453, status_code=404)
        content_changed = payload.content is not None and payload.content != row.content
        if payload.content is not None:
            row.content = payload.content
            row.char_count = len(payload.content)
        if payload.enabled is not None:
            row.enabled = payload.enabled
        row.updated_by = self.context.user_id
        if content_changed:
            from app.repositories.rag import EmbeddingRepository

            embeddings = EmbeddingRepository(self.session, self.context.tenant_id)
            await embeddings.mark_stale(row.id)
        await self.session.commit()
        if content_changed:
            from app.services.embedding import enqueue_embed_task

            document = await self._require_document(row.document_id)
            task = await enqueue_embed_task(self.session, document, self.context.user_id)
            await self.session.commit()
            if task is not None:
                await self._dispatch(task.id)
        await self.session.refresh(row)
        return self._chunk_out(row)

    async def list_tasks(
        self,
        *,
        knowledge_base_id: int | None,
        document_id: int | None,
        status: str | None,
        task_type: str | None,
        page: int,
        page_size: int,
    ) -> TaskListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        rows, total = await self.tasks.list_page(
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            status=status,
            task_type=task_type,
            page=page,
            page_size=page_size,
        )
        return TaskListOut(
            items=[self._task_out(item) for item in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_task(self, task_id: int) -> TaskOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        row = await self.tasks.get_in_tenant(task_id)
        if row is None:
            raise AppError(_UNAVAILABLE_TASK, code=40454, status_code=404)
        return self._task_out(row)

    async def retry_task(self, task_id: int) -> TaskOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self.tasks.get_in_tenant(task_id)
        if row is None:
            raise AppError(_UNAVAILABLE_TASK, code=40454, status_code=404)
        if row.status != TaskStatus.FAILED.value:
            raise AppError("仅失败任务可以重试", code=40081, status_code=400)
        document = await self._require_document(row.document_id)
        existed = await self.tasks.find_active(document.id, row.task_type)
        if existed is not None:
            raise AppError("该文档已有进行中的同类任务", code=40952, status_code=409)
        row.status = TaskStatus.QUEUED.value
        row.progress = 0
        row.attempt += 1
        row.error_message = None
        row.started_at = None
        row.finished_at = None
        if row.task_type == TaskType.PARSE.value:
            document.status = KnowledgeDocumentStatus.PENDING.value
        elif row.task_type != TaskType.EMBED.value:
            document.status = KnowledgeDocumentStatus.PROCESSING.value
        await self.session.commit()
        await self._dispatch(row.id)
        await self.session.refresh(row)
        return self._task_out(row)

    async def _create_task(
        self,
        document: KnowledgeDocument,
        task_type: str,
        payload: dict | None,
    ) -> DocumentProcessingTask:
        existed = await self.tasks.find_active(document.id, task_type)
        if existed is not None:
            raise AppError("该文档已有进行中的同类任务", code=40952, status_code=409)
        task = DocumentProcessingTask(
            tenant_id=self.context.tenant_id,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            task_type=task_type,
            status=TaskStatus.QUEUED.value,
            payload=payload,
            created_by=self.context.user_id,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def _dispatch(self, task_id: int) -> None:
        if settings.task_executor != "redis":
            await ProcessingService(self.session).execute(task_id)
            return
        await enqueue_task(task_id)

    async def _require_base(self, knowledge_base_id: int):
        row = await self.bases.get_in_tenant(knowledge_base_id)
        if row is None:
            raise AppError(_UNAVAILABLE_BASE, code=40450, status_code=404)
        return row

    async def _require_document(self, document_id: int) -> KnowledgeDocument:
        row = await self.documents.get_in_tenant(document_id)
        if row is None:
            raise AppError(_UNAVAILABLE_DOC, code=40451, status_code=404)
        return row

    @staticmethod
    def _document_out(row: KnowledgeDocument) -> DocumentOut:
        return DocumentOut(
            id=row.id,
            tenant_id=row.tenant_id,
            knowledge_base_id=row.knowledge_base_id,
            filename=row.filename,
            file_size=row.file_size,
            mime_type=row.mime_type,
            extension=row.extension,
            sha256=row.sha256,
            status=row.status,
            error_message=row.error_message,
            warning_message=row.warning_message,
            extracted_char_count=len(row.extracted_text or ""),
            chunk_strategy=row.chunk_strategy,
            chunk_size=row.chunk_size,
            chunk_overlap=row.chunk_overlap,
            chunk_unit=row.chunk_unit or "char",
            active_chunk_version=row.active_chunk_version,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _chunk_out(row) -> ChunkOut:
        return ChunkOut(
            id=row.id,
            tenant_id=row.tenant_id,
            knowledge_base_id=row.knowledge_base_id,
            document_id=row.document_id,
            version=row.version,
            chunk_index=row.chunk_index,
            content=row.content,
            char_count=row.char_count,
            page_no=row.page_no,
            heading=row.heading,
            source_start=row.source_start,
            source_end=row.source_end,
            status=row.status,
            enabled=row.enabled,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _task_out(row: DocumentProcessingTask) -> TaskOut:
        return TaskOut(
            id=row.id,
            tenant_id=row.tenant_id,
            knowledge_base_id=row.knowledge_base_id,
            document_id=row.document_id,
            task_type=row.task_type,
            status=row.status,
            progress=row.progress,
            attempt=row.attempt,
            error_message=row.error_message,
            payload=row.payload,
            started_at=row.started_at,
            finished_at=row.finished_at,
            created_at=row.created_at,
        )
