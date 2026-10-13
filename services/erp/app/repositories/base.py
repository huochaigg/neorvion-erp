from sqlalchemy.orm import Session

from app.core.exceptions import AppError


class BaseRepository:
    """数据访问基类。

    约定：
    1. 不在 Repository 内 commit / rollback，事务由 Service 控制。
    2. 业务查询必须带 tenant_id，不能信任前端传入的租户值。
    3. 业务 Repository 构造时传入已校验的 tenant_id，查询必须带该条件。
    """

    def __init__(self, session: Session, tenant_id: int | None = None) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def ensure_tenant(self) -> int:
        if self.tenant_id is None:
            raise AppError("缺少租户上下文", code=40030, status_code=400)
        return self.tenant_id
