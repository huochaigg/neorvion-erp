from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository


class WarehouseRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def list_page(
        self,
        *,
        q: str | None,
        warehouse_type: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Warehouse], int]:
        """分页列出当前租户仓库。必须带 tenant_id，不能只按名称搜全局表。"""
        tenant_id = self.ensure_tenant()
        filters = [Warehouse.tenant_id == tenant_id]
        if status:
            filters.append(Warehouse.status == status)
        if warehouse_type:
            filters.append(Warehouse.type == warehouse_type)
        if q:
            pattern = f"%{q}%"
            filters.append(or_(Warehouse.name.like(pattern), Warehouse.code.like(pattern)))
        total = int(self.session.scalar(select(func.count(Warehouse.id)).where(*filters)) or 0)
        stmt = (
            select(Warehouse)
            .where(*filters)
            .order_by(Warehouse.is_default.desc(), Warehouse.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(stmt).all()), total

    def get_in_tenant(self, warehouse_id: int) -> Warehouse | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Warehouse).where(
            Warehouse.tenant_id == tenant_id,
            Warehouse.id == warehouse_id,
        )
        return self.session.scalars(stmt).first()

    def get_by_code(self, code: str) -> Warehouse | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Warehouse).where(Warehouse.tenant_id == tenant_id, Warehouse.code == code)
        return self.session.scalars(stmt).first()

    def count_in_tenant(self) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(Warehouse.id)).where(Warehouse.tenant_id == tenant_id)
        return int(self.session.scalar(stmt) or 0)

    def lock_all_in_tenant(self) -> list[Warehouse]:
        """锁住当前租户全部仓库行，按 id 排序避免死锁。

        SELECT ... FOR UPDATE 只锁本租户匹配行，不会锁到其他企业的仓库。
        两个管理员同时改默认仓库时，后到的事务会等到前一个提交，再读到最新默认标记。
        """
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Warehouse)
            .where(Warehouse.tenant_id == tenant_id)
            .order_by(Warehouse.id.asc())
            .with_for_update()
        )
        return list(self.session.scalars(stmt).all())

    def lock_tenant(self) -> Tenant | None:
        """锁当前租户行。第一个仓库创建时表里还没有仓库行可锁，用租户行串行化。"""
        tenant_id = self.ensure_tenant()
        stmt = select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        return self.session.scalars(stmt).first()

    def add(self, warehouse: Warehouse) -> Warehouse:
        self.session.add(warehouse)
        return warehouse

    def delete(self, warehouse: Warehouse) -> None:
        self.session.delete(warehouse)
