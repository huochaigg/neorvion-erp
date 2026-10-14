"""知识库级授权。复用 ERP 用户与租户，不另建身份体系。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.knowledge import KnowledgeBase
from app.repositories.knowledge import KnowledgeBaseRepository
from app.repositories.ops import GrantRepository

_WRITE = {"WRITE", "ADMIN"}
_ADMIN = {"ADMIN"}


class AccessService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.bases = KnowledgeBaseRepository(session, context.tenant_id)
        self.grants = GrantRepository(session, context.tenant_id)

    async def readable_base_ids(self) -> list[int]:
        """当前身份可读的知识库 ID。API Key 只看 Key 绑定范围；JWT 再叠加 grants。"""
        rows, _ = await self.bases.list_page(q=None, status=None, page=1, page_size=500)
        ids = [row.id for row in rows]
        if self.context.api_key_id is not None:
            allowed = self.context.api_key_base_ids
            if allowed is None:
                return ids
            return [item for item in ids if item in allowed]
        grant_rows = await self.grants.list_for_bases(ids)
        by_base: dict[int, list] = {}
        for row in grant_rows:
            by_base.setdefault(row.knowledge_base_id, []).append(row)
        if self.context.is_owner:
            return ids
        readable: list[int] = []
        for knowledge_base_id in ids:
            grants = by_base.get(knowledge_base_id) or []
            if not grants:
                readable.append(knowledge_base_id)
            elif any(item.user_id == self.context.user_id for item in grants):
                readable.append(knowledge_base_id)
        return readable

    async def assert_readable(self, knowledge_base_id: int) -> KnowledgeBase:
        row = await self.bases.get_in_tenant(knowledge_base_id)
        if row is None:
            raise AppError("知识库不存在或不可访问", code=40450, status_code=404)
        if knowledge_base_id not in await self.readable_base_ids():
            raise AppError("知识库不存在或不可访问", code=40450, status_code=404)
        return row

    async def assert_writable(self, knowledge_base_id: int) -> KnowledgeBase:
        """写入需 JWT，且当知识库存在授权名单时要求 WRITE/ADMIN。"""
        row = await self.assert_readable(knowledge_base_id)
        if self.context.api_key_id is not None:
            raise AppError("API Key 不能修改知识库", code=40361, status_code=403)
        if self.context.is_owner:
            return row
        grants = await self.grants.list_for_base(knowledge_base_id)
        if not grants:
            return row
        grant = next((item for item in grants if item.user_id == self.context.user_id), None)
        if grant is None or grant.permission not in _WRITE:
            raise AppError("没有该知识库的写权限", code=40362, status_code=403)
        return row

    async def assert_admin(self, knowledge_base_id: int) -> KnowledgeBase:
        row = await self.assert_writable(knowledge_base_id)
        if self.context.is_owner:
            return row
        grants = await self.grants.list_for_base(knowledge_base_id)
        if not grants:
            return row
        grant = next((item for item in grants if item.user_id == self.context.user_id), None)
        if grant is None or grant.permission not in _ADMIN:
            raise AppError("没有该知识库的授权管理权限", code=40363, status_code=403)
        return row
