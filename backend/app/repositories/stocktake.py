"""盘点单持久化。不在这里 commit。"""

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.product import ProductSku
from app.models.stocktake import StocktakeItem, StocktakeOrder
from app.models.user import User
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository


class StocktakeRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, stocktake_id: int) -> StocktakeOrder | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(StocktakeOrder)
            .options(
                selectinload(StocktakeOrder.warehouse),
                selectinload(StocktakeOrder.items)
                .selectinload(StocktakeItem.sku)
                .selectinload(ProductSku.product),
            )
            .where(StocktakeOrder.tenant_id == tenant_id, StocktakeOrder.id == stocktake_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, stocktake_id: int) -> StocktakeOrder | None:
        """确认、提交、取消前锁盘点单，避免同一张单被确认两次。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(StocktakeOrder)
            .where(StocktakeOrder.tenant_id == tenant_id, StocktakeOrder.id == stocktake_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, order: StocktakeOrder) -> StocktakeOrder:
        self.session.add(order)
        return order

    def add_item(self, item: StocktakeItem) -> StocktakeItem:
        self.session.add(item)
        return item

    def list_items(self, stocktake_id: int) -> list[StocktakeItem]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(StocktakeItem)
            .where(
                StocktakeItem.tenant_id == tenant_id,
                StocktakeItem.stocktake_order_id == stocktake_id,
            )
            .order_by(StocktakeItem.sku_id.asc(), StocktakeItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get_item(self, stocktake_id: int, item_id: int) -> StocktakeItem | None:
        tenant_id = self.ensure_tenant()
        stmt = select(StocktakeItem).where(
            StocktakeItem.tenant_id == tenant_id,
            StocktakeItem.stocktake_order_id == stocktake_id,
            StocktakeItem.id == item_id,
        )
        return self.session.scalars(stmt).first()

    def count_by_warehouse(self, warehouse_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(StocktakeOrder.id)).where(
            StocktakeOrder.tenant_id == tenant_id,
            StocktakeOrder.warehouse_id == warehouse_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def list_page(
        self,
        *,
        q: str | None,
        warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        filters = [StocktakeOrder.tenant_id == tenant_id]
        if q:
            filters.append(StocktakeOrder.stocktake_no.like(f"%{q}%"))
        if warehouse_id:
            filters.append(StocktakeOrder.warehouse_id == warehouse_id)
        if status:
            filters.append(StocktakeOrder.status == status)
        if created_from is not None:
            filters.append(StocktakeOrder.created_at >= created_from)
        if created_to is not None:
            filters.append(StocktakeOrder.created_at <= created_to)
        qty = (
            select(
                StocktakeItem.stocktake_order_id.label("stocktake_id"),
                func.count(StocktakeItem.id).label("sku_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (StocktakeItem.counted_quantity.is_not(None))
                                & (StocktakeItem.difference_quantity != 0),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("difference_sku_count"),
            )
            .where(StocktakeItem.tenant_id == tenant_id)
            .group_by(StocktakeItem.stocktake_order_id)
            .subquery()
        )
        count_stmt = select(func.count(StocktakeOrder.id)).where(*filters)
        total = int(self.session.scalar(count_stmt) or 0)
        stmt = (
            select(
                StocktakeOrder,
                Warehouse.name,
                User.display_name,
                func.coalesce(qty.c.sku_count, 0),
                func.coalesce(qty.c.difference_sku_count, 0),
            )
            .join(Warehouse, Warehouse.id == StocktakeOrder.warehouse_id)
            .outerjoin(User, User.id == StocktakeOrder.created_by)
            .outerjoin(qty, qty.c.stocktake_id == StocktakeOrder.id)
            .where(*filters)
            .order_by(StocktakeOrder.created_at.desc(), StocktakeOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total
