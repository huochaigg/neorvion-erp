from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError


class BaseRepository:
    """数据访问基类。不在 Repository 内 commit；查询必须带 tenant_id。"""

    def __init__(self, session: AsyncSession, tenant_id: int | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def ensure_tenant(self) -> int:
        if self.tenant_id is None:
            raise AppError("缺少租户上下文", code=40030, status_code=400)
        return self.tenant_id
