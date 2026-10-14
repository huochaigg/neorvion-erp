from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.repositories.base import BaseRepository


class KnowledgeBaseRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    async def get_in_tenant(self, knowledge_base_id: int) -> KnowledgeBase | None:
        tenant_id = self.ensure_tenant()
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.deleted_at.is_(None),
        )
        return (await self.session.scalars(stmt)).first()

    async def get_deleted(self, knowledge_base_id: int) -> KnowledgeBase | None:
        tenant_id = self.ensure_tenant()
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.deleted_at.is_not(None),
        )
        return (await self.session.scalars(stmt)).first()

    async def list_deleted(self, *, page: int, page_size: int) -> tuple[list[KnowledgeBase], int]:
        tenant_id = self.ensure_tenant()
        filters = [KnowledgeBase.tenant_id == tenant_id, KnowledgeBase.deleted_at.is_not(None)]
        total = int(await self.session.scalar(select(func.count(KnowledgeBase.id)).where(*filters)) or 0)
        stmt = (
            select(KnowledgeBase)
            .where(*filters)
            .order_by(KnowledgeBase.deleted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def list_page(
        self,
        *,
        q: str | None,
        status: str | None,
        page: int,
        page_size: int,
        ids: list[int] | None = None,
    ) -> tuple[list[KnowledgeBase], int]:
        """分页列出当前租户未删除的知识库。必须带 tenant_id。"""
        tenant_id = self.ensure_tenant()
        filters = [KnowledgeBase.tenant_id == tenant_id, KnowledgeBase.deleted_at.is_(None)]
        if ids is not None:
            if not ids:
                return [], 0
            filters.append(KnowledgeBase.id.in_(ids))
        if status:
            filters.append(KnowledgeBase.status == status)
        if q:
            filters.append(KnowledgeBase.name.ilike(f"%{q}%"))
        total = int(
            await self.session.scalar(select(func.count(KnowledgeBase.id)).where(*filters)) or 0
        )
        stmt = (
            select(KnowledgeBase)
            .where(*filters)
            .order_by(KnowledgeBase.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await self.session.scalars(stmt)).all())
        return rows, total

    async def get_by_name(
        self,
        name: str,
        *,
        exclude_id: int | None = None,
    ) -> KnowledgeBase | None:
        tenant_id = self.ensure_tenant()
        filters = [
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.name == name,
            KnowledgeBase.deleted_at.is_(None),
        ]
        if exclude_id is not None:
            filters.append(KnowledgeBase.id != exclude_id)
        stmt = select(KnowledgeBase).where(*filters)
        return (await self.session.scalars(stmt)).first()

    async def count_documents(self, knowledge_base_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(KnowledgeDocument.id)).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
        return int(await self.session.scalar(stmt) or 0)

    async def count_documents_grouped(self, knowledge_base_ids: list[int]) -> dict[int, int]:
        if not knowledge_base_ids:
            return {}
        tenant_id = self.ensure_tenant()
        stmt = (
            select(KnowledgeDocument.knowledge_base_id, func.count(KnowledgeDocument.id))
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.knowledge_base_id.in_(knowledge_base_ids),
                KnowledgeDocument.deleted_at.is_(None),
            )
            .group_by(KnowledgeDocument.knowledge_base_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {int(base_id): int(count) for base_id, count in rows}

    def add(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        self.session.add(knowledge_base)
        return knowledge_base
