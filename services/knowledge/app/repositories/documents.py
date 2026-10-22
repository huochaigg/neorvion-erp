from datetime import UTC, datetime

from neorvion_db import PrivilegedOperation, privileged_option
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    ChunkStatus,
    DocumentChunk,
    DocumentProcessingTask,
    KnowledgeBase,
    KnowledgeDocument,
    TaskStatus,
)
from app.repositories.base import BaseRepository


def live_chunk_parent_filters():
    """业务列表/统计/检索共用：父文档与知识库均未软删除。不给切片表加 deleted_at。"""
    return (
        KnowledgeDocument.tenant_id == DocumentChunk.tenant_id,
        KnowledgeDocument.id == DocumentChunk.document_id,
        KnowledgeDocument.deleted_at.is_(None),
        KnowledgeBase.tenant_id == DocumentChunk.tenant_id,
        KnowledgeBase.id == DocumentChunk.knowledge_base_id,
        KnowledgeBase.deleted_at.is_(None),
    )


async def get_live_document(session: AsyncSession, tenant_id: int, document_id: int) -> KnowledgeDocument | None:
    """文档与所属知识库均未软删除时返回文档。Worker 写入切片/向量前必须再查一次。"""
    return await session.scalar(
        select(KnowledgeDocument)
        .join(
            KnowledgeBase,
            and_(
                KnowledgeBase.tenant_id == KnowledgeDocument.tenant_id,
                KnowledgeBase.id == KnowledgeDocument.knowledge_base_id,
            ),
        )
        .where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeBase.deleted_at.is_(None),
        )
    )


class DocumentRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def _base_filters(self):
        tenant_id = self.ensure_tenant()
        return [
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.deleted_at.is_(None),
        ]

    async def list_page(
        self,
        *,
        knowledge_base_id: int | None,
        q: str | None,
        status: str | None,
        page: int,
        page_size: int,
        knowledge_base_ids: list[int] | None = None,
    ) -> tuple[list[KnowledgeDocument], int]:
        filters = self._base_filters()
        if knowledge_base_id is not None:
            filters.append(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
        if knowledge_base_ids is not None:
            if not knowledge_base_ids:
                return [], 0
            filters.append(KnowledgeDocument.knowledge_base_id.in_(knowledge_base_ids))
        if status:
            filters.append(KnowledgeDocument.status == status)
        if q:
            filters.append(KnowledgeDocument.filename.ilike(f"%{q}%"))
        total = int(
            await self.session.scalar(select(func.count(KnowledgeDocument.id)).where(*filters)) or 0
        )
        stmt = (
            select(KnowledgeDocument)
            .where(*filters)
            .order_by(KnowledgeDocument.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_in_tenant(self, document_id: int) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocument).where(
            *self._base_filters(),
            KnowledgeDocument.id == document_id,
        )
        return (await self.session.scalars(stmt)).first()

    async def get_deleted(self, document_id: int) -> KnowledgeDocument | None:
        tenant_id = self.ensure_tenant()
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.deleted_at.is_not(None),
        )
        return (await self.session.scalars(stmt)).first()

    async def list_deleted(
        self,
        *,
        knowledge_base_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[KnowledgeDocument], int]:
        tenant_id = self.ensure_tenant()
        join_base = and_(
            KnowledgeBase.tenant_id == KnowledgeDocument.tenant_id,
            KnowledgeBase.id == KnowledgeDocument.knowledge_base_id,
        )
        filters = [
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.deleted_at.is_not(None),
            KnowledgeBase.deleted_at.is_(None),
        ]
        if knowledge_base_id is not None:
            filters.append(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
        total = int(
            await self.session.scalar(
                select(func.count(KnowledgeDocument.id))
                .select_from(KnowledgeDocument)
                .join(KnowledgeBase, join_base)
                .where(*filters)
            )
            or 0
        )
        stmt = (
            select(KnowledgeDocument)
            .join(KnowledgeBase, join_base)
            .where(*filters)
            .order_by(KnowledgeDocument.deleted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def list_cascade_deleted_for_base(
        self, knowledge_base_id: int, *, cascade_at: datetime
    ) -> list[KnowledgeDocument]:
        """知识库软删除时一并盖戳的文档。时间戳与库的 deleted_at 相同，不含事先单独删除的文档。"""
        tenant_id = self.ensure_tenant()
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.deleted_at == cascade_at,
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_including_deleted_for_base(self, knowledge_base_id: int) -> list[KnowledgeDocument]:
        tenant_id = self.ensure_tenant()
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
        )
        return list((await self.session.scalars(stmt)).all())

    async def live_ids(self, document_ids: list[int]) -> set[int]:
        """返回仍可打开详情的文档 ID（文档与所属知识库均未软删除）。"""
        if not document_ids:
            return set()
        tenant_id = self.ensure_tenant()
        stmt = (
            select(KnowledgeDocument.id)
            .join(
                KnowledgeBase,
                (KnowledgeBase.tenant_id == KnowledgeDocument.tenant_id)
                & (KnowledgeBase.id == KnowledgeDocument.knowledge_base_id),
            )
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.id.in_(document_ids),
                KnowledgeDocument.deleted_at.is_(None),
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        return set((await self.session.scalars(stmt)).all())

    async def get_by_sha256(self, knowledge_base_id: int, sha256: str) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocument).where(
            *self._base_filters(),
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.sha256 == sha256,
        )
        return (await self.session.scalars(stmt)).first()

    async def list_recent(self, limit: int = 8) -> list[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocument)
            .where(*self._base_filters())
            .order_by(KnowledgeDocument.id.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_by_status(self) -> dict[str, int]:
        stmt = (
            select(KnowledgeDocument.status, func.count(KnowledgeDocument.id))
            .where(*self._base_filters())
            .group_by(KnowledgeDocument.status)
        )
        rows = (await self.session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    def add(self, document: KnowledgeDocument) -> KnowledgeDocument:
        self.session.add(document)
        return document


class ChunkRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    async def list_active(
        self,
        *,
        document_id: int | None,
        knowledge_base_id: int | None,
        enabled: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[DocumentChunk], int]:
        tenant_id = self.ensure_tenant()
        filters = [
            DocumentChunk.tenant_id == tenant_id,
            DocumentChunk.status == ChunkStatus.ACTIVE.value,
            *live_chunk_parent_filters(),
        ]
        if document_id is not None:
            filters.append(DocumentChunk.document_id == document_id)
        if knowledge_base_id is not None:
            filters.append(DocumentChunk.knowledge_base_id == knowledge_base_id)
        if enabled is not None:
            filters.append(DocumentChunk.enabled.is_(enabled))
        total = int(
            await self.session.scalar(
                select(func.count(DocumentChunk.id))
                .select_from(DocumentChunk)
                .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
                .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
                .where(*filters)
            )
            or 0
        )
        stmt = (
            select(DocumentChunk)
            .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
            .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
            .where(*filters)
            .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_in_tenant(self, chunk_id: int) -> DocumentChunk | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(DocumentChunk)
            .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
            .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.id == chunk_id,
                *live_chunk_parent_filters(),
            )
        )
        return (await self.session.scalars(stmt)).first()

    async def count_active(self) -> int:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(func.count(DocumentChunk.id))
            .select_from(DocumentChunk)
            .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
            .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.status == ChunkStatus.ACTIVE.value,
                *live_chunk_parent_filters(),
            )
        )
        return int(await self.session.scalar(stmt) or 0)

    async def delete_version(self, document_id: int, version: int) -> None:
        tenant_id = self.ensure_tenant()
        rows = list(
            (
                await self.session.scalars(
                    select(DocumentChunk).where(
                        DocumentChunk.tenant_id == tenant_id,
                        DocumentChunk.document_id == document_id,
                        DocumentChunk.version == version,
                    )
                )
            ).all()
        )
        for row in rows:
            await self.session.delete(row)

    async def supersede_active(self, document_id: int) -> None:
        tenant_id = self.ensure_tenant()
        await self.session.execute(
            update(DocumentChunk)
            .where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_id == document_id,
                DocumentChunk.status == ChunkStatus.ACTIVE.value,
            )
            .values(status=ChunkStatus.SUPERSEDED.value)
        )

    async def delete_all_for_document(self, document_id: int) -> None:
        tenant_id = self.ensure_tenant()
        rows = list(
            (
                await self.session.scalars(
                    select(DocumentChunk).where(
                        DocumentChunk.tenant_id == tenant_id,
                        DocumentChunk.document_id == document_id,
                    )
                )
            ).all()
        )
        for row in rows:
            await self.session.delete(row)


class TaskRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int | None = None) -> None:
        super().__init__(session, tenant_id)

    async def list_page(
        self,
        *,
        knowledge_base_id: int | None,
        document_id: int | None,
        status: str | None,
        task_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[DocumentProcessingTask], int]:
        tenant_id = self.ensure_tenant()
        filters = [DocumentProcessingTask.tenant_id == tenant_id]
        if knowledge_base_id is not None:
            filters.append(DocumentProcessingTask.knowledge_base_id == knowledge_base_id)
        if document_id is not None:
            filters.append(DocumentProcessingTask.document_id == document_id)
        if status:
            filters.append(DocumentProcessingTask.status == status)
        if task_type:
            filters.append(DocumentProcessingTask.task_type == task_type)
        total = int(
            await self.session.scalar(select(func.count(DocumentProcessingTask.id)).where(*filters)) or 0
        )
        stmt = (
            select(DocumentProcessingTask)
            .where(*filters)
            .order_by(DocumentProcessingTask.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_in_tenant(self, task_id: int) -> DocumentProcessingTask | None:
        tenant_id = self.ensure_tenant()
        stmt = select(DocumentProcessingTask).where(
            DocumentProcessingTask.tenant_id == tenant_id,
            DocumentProcessingTask.id == task_id,
        )
        return (await self.session.scalars(stmt)).first()

    async def get_by_id(self, task_id: int) -> DocumentProcessingTask | None:
        stmt = select(DocumentProcessingTask).where(DocumentProcessingTask.id == task_id)
        return (await self.session.scalars(stmt)).first()

    async def find_active(self, document_id: int, task_type: str) -> DocumentProcessingTask | None:
        tenant_id = self.ensure_tenant()
        stmt = select(DocumentProcessingTask).where(
            DocumentProcessingTask.tenant_id == tenant_id,
            DocumentProcessingTask.document_id == document_id,
            DocumentProcessingTask.task_type == task_type,
            DocumentProcessingTask.status.in_((TaskStatus.QUEUED.value, TaskStatus.RUNNING.value)),
        )
        return (await self.session.scalars(stmt)).first()

    async def list_pending(self, limit: int = 20) -> list[DocumentProcessingTask]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(DocumentProcessingTask)
            .where(
                DocumentProcessingTask.tenant_id == tenant_id,
                DocumentProcessingTask.status.in_((TaskStatus.QUEUED.value, TaskStatus.FAILED.value)),
            )
            .order_by(DocumentProcessingTask.id.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_by_status(self, statuses: tuple[str, ...]) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(DocumentProcessingTask.id)).where(
            DocumentProcessingTask.tenant_id == tenant_id,
            DocumentProcessingTask.status.in_(statuses),
        )
        return int(await self.session.scalar(stmt) or 0)

    async def delete_for_document(self, document_id: int) -> None:
        """彻底删除文档前先卸掉处理任务，避免 ORM 把 NOT NULL 的 document_id/tenant_id 置空。"""
        tenant_id = self.ensure_tenant()
        await self.session.execute(
            delete(DocumentProcessingTask).where(
                DocumentProcessingTask.tenant_id == tenant_id,
                DocumentProcessingTask.document_id == document_id,
            )
        )

    async def list_queued(self) -> list[DocumentProcessingTask]:
        stmt = (
            select(DocumentProcessingTask)
            .where(DocumentProcessingTask.status == TaskStatus.QUEUED.value)
            .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
        )
        return list((await self.session.scalars(stmt)).all())

    async def fail_stale_running(self, *, message: str) -> list[DocumentProcessingTask]:
        stmt = (
            select(DocumentProcessingTask)
            .where(DocumentProcessingTask.status == TaskStatus.RUNNING.value)
            .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
        )
        rows = list((await self.session.scalars(stmt)).all())
        now = datetime.now(UTC)
        for row in rows:
            row.status = TaskStatus.FAILED.value
            row.error_message = message
            row.finished_at = now
        return rows
