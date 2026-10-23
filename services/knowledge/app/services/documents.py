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
from app.models.ops import DocumentRevision
from app.processing.extract import sniff_kind
from app.processing.split import validate_chunk_params
from app.processing.storage import (
    build_revision_key,
    build_storage_key,
    delete_document_files,
    ensure_allowed_extension,
    read_bytes,
    resolve_stored_path,
    sanitize_filename,
    sha256_bytes,
    write_bytes,
)
from app.repositories.documents import ChunkRepository, DocumentRepository, TaskRepository
from app.repositories.knowledge import KnowledgeBaseRepository
from app.repositories.ops import RevisionRepository
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
from app.schemas.ops import (
    RecycleBatchOut,
    RecycleItemOut,
    RecycleListOut,
    RevisionListOut,
    RevisionOut,
)
from app.services.access import AccessService
from app.services.audit import write_audit
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
        self.revisions = RevisionRepository(session, context.tenant_id)
        self.access = AccessService(session, context)

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
        readable = await self.access.readable_base_ids()
        if knowledge_base_id is not None:
            await self.access.assert_readable(knowledge_base_id)
        rows, total = await self.documents.list_page(
            knowledge_base_id=knowledge_base_id,
            q=(q or "").strip() or None,
            status=status,
            page=page,
            page_size=page_size,
            knowledge_base_ids=None if knowledge_base_id is not None else readable,
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
        await self.access.assert_writable(knowledge_base_id)
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
        """软删除文档。文件、切片和向量保留到彻底清理，检索会因 deleted_at 自动排除。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self._require_document(document_id)
        await self.access.assert_writable(row.knowledge_base_id)
        for task_type in (TaskType.PARSE.value, TaskType.CHUNK.value, TaskType.EMBED.value):
            found = await self.tasks.find_active(row.id, task_type)
            if found is not None:
                found.status = TaskStatus.FAILED.value
                found.error_message = "文档已删除，任务取消"
                found.finished_at = datetime.now(UTC)
        row.deleted_at = datetime.now(UTC)
        row.updated_by = self.context.user_id
        await write_audit(
            self.session,
            self.context,
            action="document.recycle",
            resource_type="document",
            resource_id=row.id,
            detail={"filename": row.filename, "knowledge_base_id": row.knowledge_base_id},
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

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
        await self.access.assert_readable(row.knowledge_base_id)
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
        live_ids = await self.documents.live_ids([item.document_id for item in rows])
        return TaskListOut(
            items=[self._task_out(item, document_available=item.document_id in live_ids) for item in rows],
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

    async def restore_document(self, document_id: int) -> DocumentOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self.documents.get_deleted(document_id)
        if row is None:
            raise AppError(_UNAVAILABLE_DOC, code=40451, status_code=404)
        base = await self.bases.get_in_tenant(row.knowledge_base_id)
        if base is None:
            raise AppError("请先恢复所属知识库", code=40063, status_code=400)
        await self.access.assert_writable(base.id)
        existed = await self.documents.get_by_sha256(row.knowledge_base_id, row.sha256)
        if existed is not None and existed.id != row.id:
            raise AppError("相同内容的文件已存在，无法恢复", code=40951, status_code=409)
        row.deleted_at = None
        row.updated_by = self.context.user_id
        await self.refresh_index_after_restore(row)
        await write_audit(
            self.session,
            self.context,
            action="document.restore",
            resource_type="document",
            resource_id=row.id,
            detail={"filename": row.filename, "status": row.status},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return self._document_out(row)

    async def refresh_index_after_restore(self, row: KnowledgeDocument) -> None:
        """恢复后核对 ACTIVE Chunk 与 READY 向量。匹配则可检索，否则进入待重新索引。"""
        from sqlalchemy import func, select

        from app.models.knowledge import ChunkStatus, DocumentChunk
        from app.models.rag import ChunkEmbedding, EmbeddingStatus
        from app.services.embedding import enqueue_embed_task

        live_chunks = int(
            await self.session.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.tenant_id == row.tenant_id,
                    DocumentChunk.document_id == row.id,
                    DocumentChunk.status == ChunkStatus.ACTIVE.value,
                    DocumentChunk.version == row.active_chunk_version,
                    DocumentChunk.enabled.is_(True),
                )
            )
            or 0
        )
        if live_chunks == 0:
            row.status = KnowledgeDocumentStatus.PENDING.value
            row.error_message = "恢复后缺少有效切片，请重新解析或切片"
            return
        ready = int(
            await self.session.scalar(
                select(func.count(ChunkEmbedding.id)).where(
                    ChunkEmbedding.tenant_id == row.tenant_id,
                    ChunkEmbedding.document_id == row.id,
                    ChunkEmbedding.status == EmbeddingStatus.READY.value,
                    ChunkEmbedding.chunk_version == row.active_chunk_version,
                    ChunkEmbedding.model_name == settings.embedding_model,
                    ChunkEmbedding.dimensions == settings.embedding_dimensions,
                )
            )
            or 0
        )
        if ready >= live_chunks:
            row.status = KnowledgeDocumentStatus.COMPLETED.value
            row.error_message = None
            return
        row.status = KnowledgeDocumentStatus.PROCESSING.value
        row.error_message = "恢复后索引不完整，已排队重建向量"
        await enqueue_embed_task(self.session, row, self.context.user_id)

    async def purge_document(self, document_id: int) -> None:
        """彻底删除文档文件、版本快照、切片和向量。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self.documents.get_deleted(document_id)
        if row is None:
            raise AppError("只能清理回收站中的文档", code=40064, status_code=400)
        from app.repositories.rag import EmbeddingRepository

        await self.tasks.delete_for_document(row.id)
        await EmbeddingRepository(self.session, self.context.tenant_id).delete_for_document(row.id)
        await self.revisions.delete_for_document(row.id)
        await self.chunks.delete_all_for_document(row.id)
        self.session.expire(row, ["tasks", "chunks"])
        await write_audit(
            self.session,
            self.context,
            action="document.purge",
            resource_type="document",
            resource_id=row.id,
            detail={"filename": row.filename},
        )
        await self.session.delete(row)
        await self.session.commit()
        try:
            delete_document_files(row.tenant_id, row.knowledge_base_id, row.id)
        except Exception:
            await write_audit(
                self.session,
                self.context,
                action="document.purge_files_pending",
                resource_type="document",
                resource_id=row.id,
                detail={"storage_key": row.storage_key, "retry": True},
            )
            await self.session.commit()

    async def list_recycle(self, *, page: int, page_size: int) -> RecycleListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        bases, base_total = await self.bases.list_deleted(page=1, page_size=500)
        docs, doc_total = await self.documents.list_deleted(
            knowledge_base_id=None, page=1, page_size=500
        )
        items = [
            RecycleItemOut(
                resource_type="knowledge_base",
                id=item.id,
                knowledge_base_id=item.id,
                name=item.name,
                deleted_at=item.deleted_at,
                deleted_by=item.updated_by,
            )
            for item in bases
            if item.deleted_at is not None
        ]
        items.extend(
            RecycleItemOut(
                resource_type="document",
                id=item.id,
                knowledge_base_id=item.knowledge_base_id,
                name=item.filename,
                deleted_at=item.deleted_at,
                deleted_by=item.updated_by,
            )
            for item in docs
            if item.deleted_at is not None
        )
        items.sort(key=lambda item: item.deleted_at, reverse=True)
        start = (page - 1) * page_size
        return RecycleListOut(
            items=items[start : start + page_size],
            total=base_total + doc_total,
            page=page,
            page_size=page_size,
        )

    async def _all_recycle_items(self) -> list[RecycleItemOut]:
        listed = await self.list_recycle(page=1, page_size=100)
        return list(listed.items)

    async def restore_recycle_batch(self, targets: list[tuple[str, int]]) -> RecycleBatchOut:
        """批量恢复。知识库优先，以便随后恢复其下文档。单项失败不回滚已成功项。"""
        from app.services.knowledge import KnowledgeBaseService

        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        unique = _unique_recycle_targets(targets)
        unique.sort(key=lambda item: 0 if item[0] == "knowledge_base" else 1)
        result = RecycleBatchOut()
        kb = KnowledgeBaseService(self.session, self.context)
        for resource_type, resource_id in unique:
            try:
                if resource_type == "knowledge_base":
                    await kb.restore_knowledge_base(resource_id)
                elif resource_type == "document":
                    await self.restore_document(resource_id)
                else:
                    raise AppError("不支持的回收站类型", code=40065, status_code=400)
                result.succeeded += 1
            except AppError as exc:
                if exc.status_code == 404:
                    result.skipped += 1
                    continue
                result.failed += 1
                result.errors.append(
                    {"resource_type": resource_type, "id": resource_id, "message": exc.message}
                )
            except Exception:
                result.failed += 1
                result.errors.append(
                    {"resource_type": resource_type, "id": resource_id, "message": "恢复失败"}
                )
        remaining = await self.list_recycle(page=1, page_size=1)
        result.remaining = remaining.total
        return result

    async def purge_recycle_batch(self, targets: list[tuple[str, int]]) -> RecycleBatchOut:
        """批量彻底删除。先删文档再删知识库，避免库先删导致文档路径丢失。"""
        from app.services.knowledge import KnowledgeBaseService

        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        unique = _unique_recycle_targets(targets)
        unique.sort(key=lambda item: 0 if item[0] == "document" else 1)
        result = RecycleBatchOut()
        kb = KnowledgeBaseService(self.session, self.context)
        for resource_type, resource_id in unique:
            try:
                if resource_type == "knowledge_base":
                    await kb.purge_knowledge_base(resource_id)
                elif resource_type == "document":
                    await self.purge_document(resource_id)
                else:
                    raise AppError("不支持的回收站类型", code=40065, status_code=400)
                result.succeeded += 1
            except AppError as exc:
                if exc.status_code == 404 or exc.code in {40062, 40064}:
                    result.skipped += 1
                    continue
                result.failed += 1
                result.errors.append(
                    {"resource_type": resource_type, "id": resource_id, "message": exc.message}
                )
            except Exception:
                result.failed += 1
                result.errors.append(
                    {"resource_type": resource_type, "id": resource_id, "message": "彻底删除失败"}
                )
        remaining = await self.list_recycle(page=1, page_size=1)
        result.remaining = remaining.total
        return result

    async def empty_recycle(self, *, confirm: bool, expected_count: int) -> RecycleBatchOut:
        """清空回收站。必须二次确认，且 expected_count 与当前条数一致，防止页面过期误删。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        if not confirm:
            raise AppError("请确认清空回收站", code=40066, status_code=400)
        listed = await self.list_recycle(page=1, page_size=500)
        if listed.total != expected_count:
            raise AppError(
                f"回收站条数已变化（当前 {listed.total}），请刷新后再清空",
                code=40960,
                status_code=409,
            )
        if listed.total > 500:
            raise AppError("单次最多清空 500 条，请分批清理", code=40067, status_code=400)
        targets = [(item.resource_type, item.id) for item in listed.items]
        return await self.purge_recycle_batch(targets)

    async def replace_document(self, document_id: int, upload: UploadFile, note: str | None) -> DocumentOut:
        """替换文档文件：先快照当前 original，再排队解析。成功前旧 ACTIVE 切片仍可检索。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._require_document(document_id)
        await self.access.assert_writable(row.knowledge_base_id)
        filename = sanitize_filename(upload.filename or row.filename)
        ext = ensure_allowed_extension(filename)
        payload = await upload.read()
        if not payload:
            raise AppError("文件为空", code=40080, status_code=400)
        if len(payload) > settings.max_upload_bytes:
            raise AppError("单个文件不能超过 20MB", code=40080, status_code=400)
        sniff_kind(filename, payload)
        digest = sha256_bytes(payload)
        existed = await self.documents.get_by_sha256(row.knowledge_base_id, digest)
        if existed is not None and existed.id != row.id:
            raise AppError("相同内容的文件已存在，已按 SHA256 去重", code=40951, status_code=409)
        current_bytes = read_bytes(row.storage_key)
        revision_no = await self.revisions.next_revision(row.id)
        old_ext = row.extension or "bin"
        snapshot_key = build_revision_key(
            self.context.tenant_id, row.knowledge_base_id, row.id, revision_no, old_ext
        )
        write_bytes(snapshot_key, current_bytes)
        self.session.add(
            DocumentRevision(
                tenant_id=self.context.tenant_id,
                document_id=row.id,
                knowledge_base_id=row.knowledge_base_id,
                revision=revision_no,
                filename=row.filename,
                storage_key=snapshot_key,
                sha256=row.sha256,
                file_size=row.file_size,
                mime_type=row.mime_type,
                chunk_version=row.active_chunk_version,
                note=note,
                created_by=self.context.user_id,
            )
        )
        row.filename = filename
        row.extension = ext
        row.mime_type = _ALLOWED_MIME.get(ext, upload.content_type or row.mime_type)
        row.sha256 = digest
        row.file_size = len(payload)
        row.storage_key = build_storage_key(self.context.tenant_id, row.knowledge_base_id, row.id, ext)
        row.status = KnowledgeDocumentStatus.PENDING.value
        row.error_message = None
        row.updated_by = self.context.user_id
        write_bytes(row.storage_key, payload)
        task = await self._create_task(row, TaskType.PARSE.value, payload=None)
        await write_audit(
            self.session,
            self.context,
            action="document.replace",
            resource_type="document",
            resource_id=row.id,
            detail={"filename": filename, "revision": revision_no},
        )
        await self.session.commit()
        await self._dispatch(task.id)
        await self.session.refresh(row)
        return self._document_out(row)

    async def list_revisions(self, document_id: int) -> RevisionListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        row = await self._require_document(document_id)
        await self.access.assert_readable(row.knowledge_base_id)
        items = await self.revisions.list_for_document(row.id)
        return RevisionListOut(
            items=[
                RevisionOut(
                    id=item.id,
                    document_id=item.document_id,
                    revision=item.revision,
                    filename=item.filename,
                    sha256=item.sha256,
                    file_size=item.file_size,
                    mime_type=item.mime_type,
                    chunk_version=item.chunk_version,
                    note=item.note,
                    created_by=item.created_by,
                    created_at=item.created_at,
                )
                for item in items
            ]
        )

    async def restore_revision(self, document_id: int, revision_id: int) -> DocumentOut:
        """把历史文件复制回 original 并重新解析。旧 ACTIVE 索引在新版本发布前保持可用。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._require_document(document_id)
        await self.access.assert_writable(row.knowledge_base_id)
        snapshot = await self.revisions.get_in_tenant(revision_id)
        if snapshot is None or snapshot.document_id != row.id:
            raise AppError("版本不存在或不可访问", code=40456, status_code=404)
        payload = read_bytes(snapshot.storage_key)
        current_bytes = read_bytes(row.storage_key)
        revision_no = await self.revisions.next_revision(row.id)
        current_key = build_revision_key(
            self.context.tenant_id, row.knowledge_base_id, row.id, revision_no, row.extension or "bin"
        )
        write_bytes(current_key, current_bytes)
        self.session.add(
            DocumentRevision(
                tenant_id=self.context.tenant_id,
                document_id=row.id,
                knowledge_base_id=row.knowledge_base_id,
                revision=revision_no,
                filename=row.filename,
                storage_key=current_key,
                sha256=row.sha256,
                file_size=row.file_size,
                mime_type=row.mime_type,
                chunk_version=row.active_chunk_version,
                note=f"恢复前快照，来自版本 {snapshot.revision}",
                created_by=self.context.user_id,
            )
        )
        ext = snapshot.filename.rsplit(".", 1)[-1].lower() if "." in snapshot.filename else row.extension
        row.filename = snapshot.filename
        row.extension = ext
        row.mime_type = snapshot.mime_type
        row.sha256 = snapshot.sha256
        row.file_size = snapshot.file_size
        row.storage_key = build_storage_key(self.context.tenant_id, row.knowledge_base_id, row.id, ext)
        row.status = KnowledgeDocumentStatus.PENDING.value
        row.updated_by = self.context.user_id
        write_bytes(row.storage_key, payload)
        task = await self._create_task(row, TaskType.PARSE.value, payload=None)
        await write_audit(
            self.session,
            self.context,
            action="document.restore_revision",
            resource_type="document",
            resource_id=row.id,
            detail={"from_revision": snapshot.revision},
        )
        await self.session.commit()
        await self._dispatch(task.id)
        await self.session.refresh(row)
        return self._document_out(row)

    async def _require_base(self, knowledge_base_id: int):
        return await self.access.assert_readable(knowledge_base_id)

    async def _require_document(self, document_id: int) -> KnowledgeDocument:
        row = await self.documents.get_in_tenant(document_id)
        if row is None:
            raise AppError(_UNAVAILABLE_DOC, code=40451, status_code=404)
        await self.access.assert_readable(row.knowledge_base_id)
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
    def _task_out(row: DocumentProcessingTask, *, document_available: bool = True) -> TaskOut:
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
            document_available=document_available,
        )


def _unique_recycle_targets(targets: list[tuple[str, int]]) -> list[tuple[str, int]]:
    seen: set[tuple[str, int]] = set()
    unique: list[tuple[str, int]] = []
    for resource_type, resource_id in targets:
        key = (resource_type, resource_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique
