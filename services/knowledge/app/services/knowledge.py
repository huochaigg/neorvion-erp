"""知识库业务规则。Repository 不 commit；写操作由本层提交。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.knowledge import KnowledgeBase, KnowledgeBaseStatus
from app.models.ops import KnowledgeBaseGrant
from app.repositories.knowledge import KnowledgeBaseRepository
from app.repositories.ops import GrantRepository
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseListOut,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.schemas.ops import GrantCreateIn, GrantListOut, GrantOut
from app.services.access import AccessService
from app.services.audit import write_audit
from app.services.authorization import AuthorizationService

_UNAVAILABLE = "知识库不存在或不可访问"
_STATUSES = {item.value for item in KnowledgeBaseStatus}


class KnowledgeBaseService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()
        self.bases = KnowledgeBaseRepository(session, context.tenant_id)
        self.grants = GrantRepository(session, context.tenant_id)
        self.access = AccessService(session, context)

    async def list_knowledge_bases(
        self,
        *,
        q: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> KnowledgeBaseListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        if status and status not in _STATUSES:
            raise AppError("知识库状态不合法", code=40061, status_code=400)
        readable = await self.access.readable_base_ids()
        rows, total = await self.bases.list_page(
            q=(q or "").strip() or None,
            status=status,
            page=page,
            page_size=page_size,
            ids=readable,
        )
        counts = await self.bases.count_documents_grouped([row.id for row in rows])
        return KnowledgeBaseListOut(
            items=[self._to_out(row, counts.get(row.id, 0)) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_knowledge_base(self, knowledge_base_id: int) -> KnowledgeBaseOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        row = await self.access.assert_readable(knowledge_base_id)
        count = await self.bases.count_documents(row.id)
        return self._to_out(row, count)

    async def create_knowledge_base(self, payload: KnowledgeBaseCreate) -> KnowledgeBaseOut:
        """创建当前租户知识库。名称在未删除记录中唯一。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_CREATE,))
        if await self.bases.get_by_name(payload.name) is not None:
            raise AppError("知识库名称已存在", code=40950, status_code=409)
        row = KnowledgeBase(
            tenant_id=self.context.tenant_id,
            name=payload.name,
            description=payload.description,
            status=KnowledgeBaseStatus.ACTIVE.value,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.bases.add(row)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise AppError("知识库名称已存在", code=40950, status_code=409) from None
        except Exception:
            await self.session.rollback()
            raise
        await write_audit(
            self.session,
            self.context,
            action="knowledge_base.create",
            resource_type="knowledge_base",
            resource_id=row.id,
            detail={"name": row.name},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_out(row, 0)

    async def update_knowledge_base(
        self,
        knowledge_base_id: int,
        payload: KnowledgeBaseUpdate,
    ) -> KnowledgeBaseOut:
        """编辑名称、描述或状态。禁止改 tenant_id / created_by。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self.access.assert_writable(knowledge_base_id)
        if payload.name is not None:
            existed = await self.bases.get_by_name(payload.name, exclude_id=row.id)
            if existed is not None:
                raise AppError("知识库名称已存在", code=40950, status_code=409)
            row.name = payload.name
        if "description" in payload.model_fields_set:
            row.description = payload.description
        if payload.status is not None:
            if payload.status not in _STATUSES:
                raise AppError("知识库状态不合法", code=40061, status_code=400)
            row.status = payload.status
        row.updated_by = self.context.user_id
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise AppError("知识库名称已存在", code=40950, status_code=409) from None
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(row)
        count = await self.bases.count_documents(row.id)
        return self._to_out(row, count)

    async def delete_knowledge_base(self, knowledge_base_id: int) -> None:
        """软删除知识库与下属文档。文件、切片和向量保留到彻底清理，避免破坏可恢复索引。"""
        from app.models.knowledge import TaskStatus, TaskType
        from app.repositories.documents import DocumentRepository, TaskRepository

        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self.access.assert_writable(knowledge_base_id)
        documents = DocumentRepository(self.session, self.context.tenant_id)
        tasks = TaskRepository(self.session, self.context.tenant_id)
        docs, _ = await documents.list_page(
            knowledge_base_id=row.id, q=None, status=None, page=1, page_size=500
        )
        now = datetime.now(UTC)
        for document in docs:
            for task_type in (TaskType.PARSE.value, TaskType.CHUNK.value, TaskType.EMBED.value):
                found = await tasks.find_active(document.id, task_type)
                if found is not None:
                    found.status = TaskStatus.FAILED.value
                    found.error_message = "知识库已删除，任务取消"
                    found.finished_at = now
            document.deleted_at = now
            document.updated_by = self.context.user_id
        from app.repositories.evaluation import EvaluationRepository

        await EvaluationRepository(self.session, self.context.tenant_id).request_cancel_for_knowledge_base(row.id)
        row.deleted_at = now
        row.updated_by = self.context.user_id
        await write_audit(
            self.session,
            self.context,
            action="knowledge_base.recycle",
            resource_type="knowledge_base",
            resource_id=row.id,
            detail={"name": row.name, "document_count": len(docs)},
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def restore_knowledge_base(self, knowledge_base_id: int) -> KnowledgeBaseOut:
        """从回收站恢复知识库，以及删除该库时一并带入回收站的文档。

        删除知识库之前就已经单独软删除的文档保持 deleted_at，不会被错误恢复。
        """
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self.bases.get_deleted(knowledge_base_id)
        if row is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        if await self.bases.get_by_name(row.name) is not None:
            raise AppError("已存在同名知识库，请先改名再恢复", code=40950, status_code=409)
        from app.repositories.documents import DocumentRepository

        documents = DocumentRepository(self.session, self.context.tenant_id)
        cascade_at = row.deleted_at
        cascade_docs = (
            await documents.list_cascade_deleted_for_base(row.id, cascade_at=cascade_at)
            if cascade_at is not None
            else []
        )
        row.deleted_at = None
        row.updated_by = self.context.user_id
        for document in cascade_docs:
            document.deleted_at = None
            document.updated_by = self.context.user_id
        await write_audit(
            self.session,
            self.context,
            action="knowledge_base.restore",
            resource_type="knowledge_base",
            resource_id=row.id,
            detail={"name": row.name, "restored_documents": len(cascade_docs)},
        )
        await self.session.commit()
        from app.services.documents import DocumentService

        doc_service = DocumentService(self.session, self.context)
        for document in cascade_docs:
            await doc_service.refresh_index_after_restore(document)
        await self.session.commit()
        await self.session.refresh(row)
        return self._to_out(row, await self.bases.count_documents(row.id))

    async def purge_knowledge_base(self, knowledge_base_id: int) -> None:
        """彻底删除：切片、向量、文件、授权与知识库行。仅回收站中的记录可清理。"""
        from app.processing.storage import delete_document_files
        from app.repositories.documents import ChunkRepository, DocumentRepository, TaskRepository
        from app.repositories.ops import RevisionRepository
        from app.repositories.rag import EmbeddingRepository

        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self.bases.get_deleted(knowledge_base_id)
        if row is None:
            raise AppError("只能清理回收站中的知识库", code=40062, status_code=400)
        documents = DocumentRepository(self.session, self.context.tenant_id)
        chunks = ChunkRepository(self.session, self.context.tenant_id)
        tasks = TaskRepository(self.session, self.context.tenant_id)
        embeddings = EmbeddingRepository(self.session, self.context.tenant_id)
        revisions = RevisionRepository(self.session, self.context.tenant_id)
        docs = await documents.list_including_deleted_for_base(row.id)
        for document in docs:
            await tasks.delete_for_document(document.id)
            await embeddings.delete_for_document(document.id)
            await revisions.delete_for_document(document.id)
            await chunks.delete_all_for_document(document.id)
            self.session.expire(document, ["tasks", "chunks"])
            await self.session.delete(document)
        grants = await self.grants.list_for_base(row.id)
        for grant in grants:
            await self.session.delete(grant)
        await write_audit(
            self.session,
            self.context,
            action="knowledge_base.purge",
            resource_type="knowledge_base",
            resource_id=row.id,
            detail={"name": row.name},
        )
        await self.session.delete(row)
        await self.session.commit()
        pending_ids: list[int] = []
        for document in docs:
            try:
                delete_document_files(document.tenant_id, document.knowledge_base_id, document.id)
            except Exception:
                pending_ids.append(document.id)
        if pending_ids:
            await write_audit(
                self.session,
                self.context,
                action="knowledge_base.purge_files_pending",
                resource_type="knowledge_base",
                resource_id=knowledge_base_id,
                detail={"pending_document_ids": pending_ids, "retry": True},
            )
            await self.session.commit()

    async def list_grants(self, knowledge_base_id: int) -> GrantListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        await self.access.assert_readable(knowledge_base_id)
        rows = await self.grants.list_for_base(knowledge_base_id)
        return GrantListOut(
            items=[
                GrantOut(
                    id=item.id,
                    knowledge_base_id=item.knowledge_base_id,
                    user_id=item.user_id,
                    permission=item.permission,
                    created_by=item.created_by,
                    created_at=item.created_at,
                )
                for item in rows
            ],
            restricted=bool(rows),
        )

    async def upsert_grant(self, knowledge_base_id: int, payload: GrantCreateIn) -> GrantOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        await self.access.assert_admin(knowledge_base_id)
        row = await self.grants.get_user_grant(knowledge_base_id, payload.user_id)
        if row is None:
            row = KnowledgeBaseGrant(
                tenant_id=self.context.tenant_id,
                knowledge_base_id=knowledge_base_id,
                user_id=payload.user_id,
                permission=payload.permission,
                created_by=self.context.user_id,
            )
            self.session.add(row)
        else:
            row.permission = payload.permission
        await write_audit(
            self.session,
            self.context,
            action="knowledge_base.grant",
            resource_type="knowledge_base",
            resource_id=knowledge_base_id,
            detail={"user_id": payload.user_id, "permission": payload.permission},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return GrantOut(
            id=row.id,
            knowledge_base_id=row.knowledge_base_id,
            user_id=row.user_id,
            permission=row.permission,
            created_by=row.created_by,
            created_at=row.created_at,
        )

    async def delete_grant(self, knowledge_base_id: int, grant_id: int) -> None:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        await self.access.assert_admin(knowledge_base_id)
        row = await self.grants.get_in_tenant(grant_id)
        if row is None or row.knowledge_base_id != knowledge_base_id:
            raise AppError("授权记录不存在", code=40455, status_code=404)
        await self.session.delete(row)
        await write_audit(
            self.session,
            self.context,
            action="knowledge_base.ungrant",
            resource_type="knowledge_base",
            resource_id=knowledge_base_id,
            detail={"user_id": row.user_id},
        )
        await self.session.commit()

    async def _require(self, knowledge_base_id: int) -> KnowledgeBase:
        row = await self.bases.get_in_tenant(knowledge_base_id)
        if row is None:
            raise AppError(_UNAVAILABLE, code=40450, status_code=404)
        return row

    @staticmethod
    def _to_out(row: KnowledgeBase, document_count: int) -> KnowledgeBaseOut:
        return KnowledgeBaseOut(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            description=row.description,
            status=row.status,
            document_count=document_count,
            created_by=row.created_by,
            updated_by=row.updated_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
