from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError


class BaseRepository:
    """数据访问基类。不在 Repository 内 commit；查询必须带 tenant_id。"""

    def __init__(self, session: AsyncSession, tenant_id: int | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def ensure_tenant(self) -> int:
        """只接受已认证的正整数租户。0 不能再当作系统查询哨兵。"""
        if type(self.tenant_id) is not int or self.tenant_id <= 0:
            raise AppError("缺少租户上下文", code=40030, status_code=400)
        return self.tenant_id
