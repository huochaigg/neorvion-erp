"""知识库业务规则。Repository 不 commit；写操作由本层提交。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.knowledge import KnowledgeBase, KnowledgeBaseStatus
from app.repositories.knowledge import KnowledgeBaseRepository
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseListOut,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from app.services.authorization import AuthorizationService

_UNAVAILABLE = "知识库不存在或不可访问"
_STATUSES = {item.value for item in KnowledgeBaseStatus}


class KnowledgeBaseService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()
        self.bases = KnowledgeBaseRepository(session, context.tenant_id)

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
        rows, total = await self.bases.list_page(
            q=(q or "").strip() or None,
            status=status,
            page=page,
            page_size=page_size,
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
        row = await self._require(knowledge_base_id)
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
        await self.session.refresh(row)
        return self._to_out(row, 0)

    async def update_knowledge_base(
        self,
        knowledge_base_id: int,
        payload: KnowledgeBaseUpdate,
    ) -> KnowledgeBaseOut:
        """编辑名称、描述或状态。禁止改 tenant_id / created_by。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._require(knowledge_base_id)
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
        """软删除知识库。不级联删除文档，留给 V2 清理文件与向量。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self._require(knowledge_base_id)
        row.deleted_at = datetime.now(UTC)
        row.updated_by = self.context.user_id
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

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
