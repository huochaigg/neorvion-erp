"""V5 运营仓储。所有查询必须带 tenant_id。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops import DocumentRevision, KnowledgeApiKey, KnowledgeAuditLog, KnowledgeBaseGrant
from app.repositories.base import BaseRepository


class RevisionRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    async def list_for_document(self, document_id: int) -> list[DocumentRevision]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(DocumentRevision)
            .where(
                DocumentRevision.tenant_id == tenant_id,
                DocumentRevision.document_id == document_id,
            )
            .order_by(DocumentRevision.revision.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_in_tenant(self, revision_id: int) -> DocumentRevision | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(DocumentRevision).where(
                DocumentRevision.tenant_id == tenant_id,
                DocumentRevision.id == revision_id,
            )
        )

    async def next_revision(self, document_id: int) -> int:
        tenant_id = self.ensure_tenant()
        current = await self.session.scalar(
            select(func.max(DocumentRevision.revision)).where(
                DocumentRevision.tenant_id == tenant_id,
                DocumentRevision.document_id == document_id,
            )
        )
        return int(current or 0) + 1

    async def delete_for_document(self, document_id: int) -> list[DocumentRevision]:
        rows = await self.list_for_document(document_id)
        for row in rows:
            await self.session.delete(row)
        return rows


class GrantRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    async def list_for_base(self, knowledge_base_id: int) -> list[KnowledgeBaseGrant]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(KnowledgeBaseGrant)
            .where(
                KnowledgeBaseGrant.tenant_id == tenant_id,
                KnowledgeBaseGrant.knowledge_base_id == knowledge_base_id,
            )
            .order_by(KnowledgeBaseGrant.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_for_bases(self, knowledge_base_ids: list[int]) -> list[KnowledgeBaseGrant]:
        if not knowledge_base_ids:
            return []
        tenant_id = self.ensure_tenant()
        stmt = select(KnowledgeBaseGrant).where(
            KnowledgeBaseGrant.tenant_id == tenant_id,
            KnowledgeBaseGrant.knowledge_base_id.in_(knowledge_base_ids),
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_user_grant(self, knowledge_base_id: int, user_id: int) -> KnowledgeBaseGrant | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(KnowledgeBaseGrant).where(
                KnowledgeBaseGrant.tenant_id == tenant_id,
                KnowledgeBaseGrant.knowledge_base_id == knowledge_base_id,
                KnowledgeBaseGrant.user_id == user_id,
            )
        )

    async def get_in_tenant(self, grant_id: int) -> KnowledgeBaseGrant | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(KnowledgeBaseGrant).where(
                KnowledgeBaseGrant.tenant_id == tenant_id,
                KnowledgeBaseGrant.id == grant_id,
            )
        )


class ApiKeyRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int | None = None) -> None:
        super().__init__(session, tenant_id)

    async def list_page(self, *, page: int, page_size: int) -> tuple[list[KnowledgeApiKey], int]:
        tenant_id = self.ensure_tenant()
        filters = [KnowledgeApiKey.tenant_id == tenant_id]
        total = int(await self.session.scalar(select(func.count(KnowledgeApiKey.id)).where(*filters)) or 0)
        stmt = (
            select(KnowledgeApiKey)
            .where(*filters)
            .order_by(KnowledgeApiKey.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_in_tenant(self, key_id: int) -> KnowledgeApiKey | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(KnowledgeApiKey).where(
                KnowledgeApiKey.tenant_id == tenant_id,
                KnowledgeApiKey.id == key_id,
            )
        )

    async def get_by_hash(self, key_hash: str) -> KnowledgeApiKey | None:
        return await self.session.scalar(select(KnowledgeApiKey).where(KnowledgeApiKey.key_hash == key_hash))

    async def touch_used(self, key_id: int, tenant_id: int) -> None:
        await self.session.execute(
            update(KnowledgeApiKey)
            .where(
                KnowledgeApiKey.id == key_id,
                KnowledgeApiKey.tenant_id == tenant_id,
            )
            .values(last_used_at=datetime.now(UTC))
        )


class AuditRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    async def list_page(
        self,
        *,
        action: str | None,
        resource_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[KnowledgeAuditLog], int]:
        tenant_id = self.ensure_tenant()
        filters = [KnowledgeAuditLog.tenant_id == tenant_id]
        if action:
            filters.append(KnowledgeAuditLog.action == action)
        if resource_type:
            filters.append(KnowledgeAuditLog.resource_type == resource_type)
        total = int(await self.session.scalar(select(func.count(KnowledgeAuditLog.id)).where(*filters)) or 0)
        stmt = (
            select(KnowledgeAuditLog)
            .where(*filters)
            .order_by(KnowledgeAuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total
