"""调拨单持久化。不在这里 commit。"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.product import ProductSku
from app.models.stock_transfer import StockTransfer, StockTransferItem
from app.models.user import User
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository


class StockTransferRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, transfer_id: int) -> StockTransfer | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(StockTransfer)
            .options(
                selectinload(StockTransfer.source_warehouse),
                selectinload(StockTransfer.target_warehouse),
                selectinload(StockTransfer.items)
                .selectinload(StockTransferItem.sku)
                .selectinload(ProductSku.product),
            )
            .where(StockTransfer.tenant_id == tenant_id, StockTransfer.id == transfer_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, transfer_id: int) -> StockTransfer | None:
        """调出、调入、取消前锁调拨单。状态检查必须在锁内做，才能保证幂等。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(StockTransfer)
            .where(StockTransfer.tenant_id == tenant_id, StockTransfer.id == transfer_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, transfer: StockTransfer) -> StockTransfer:
        self.session.add(transfer)
        return transfer

    def add_item(self, item: StockTransferItem) -> StockTransferItem:
        self.session.add(item)
        return item

    def delete_items(self, transfer_id: int) -> None:
        tenant_id = self.ensure_tenant()
        rows = self.session.scalars(
            select(StockTransferItem).where(
                StockTransferItem.tenant_id == tenant_id,
                StockTransferItem.stock_transfer_id == transfer_id,
            )
        ).all()
        for row in rows:
            self.session.delete(row)

    def list_items(self, transfer_id: int) -> list[StockTransferItem]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(StockTransferItem)
            .options(selectinload(StockTransferItem.sku).selectinload(ProductSku.product))
            .where(
                StockTransferItem.tenant_id == tenant_id,
                StockTransferItem.stock_transfer_id == transfer_id,
            )
            .order_by(StockTransferItem.sku_id.asc(), StockTransferItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def count_by_warehouse(self, warehouse_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(StockTransfer.id)).where(
            StockTransfer.tenant_id == tenant_id,
            or_(
                StockTransfer.source_warehouse_id == warehouse_id,
                StockTransfer.target_warehouse_id == warehouse_id,
            ),
        )
        return int(self.session.scalar(stmt) or 0)

    def list_page(
        self,
        *,
        q: str | None,
        source_warehouse_id: int | None,
        target_warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        source = Warehouse.__table__.alias("source_wh")
        target = Warehouse.__table__.alias("target_wh")
        filters = [StockTransfer.tenant_id == tenant_id]
        if q:
            filters.append(StockTransfer.transfer_no.like(f"%{q}%"))
        if source_warehouse_id:
            filters.append(StockTransfer.source_warehouse_id == source_warehouse_id)
        if target_warehouse_id:
            filters.append(StockTransfer.target_warehouse_id == target_warehouse_id)
        if status:
            filters.append(StockTransfer.status == status)
        if created_from is not None:
            filters.append(StockTransfer.created_at >= created_from)
        if created_to is not None:
            filters.append(StockTransfer.created_at <= created_to)
        qty = (
            select(
                StockTransferItem.stock_transfer_id.label("transfer_id"),
                func.count(StockTransferItem.id).label("sku_count"),
                func.coalesce(func.sum(StockTransferItem.quantity), 0).label("total_quantity"),
            )
            .where(StockTransferItem.tenant_id == tenant_id)
            .group_by(StockTransferItem.stock_transfer_id)
            .subquery()
        )
        count_stmt = select(func.count(StockTransfer.id)).where(*filters)
        total = int(self.session.scalar(count_stmt) or 0)
        stmt = (
            select(
                StockTransfer,
                source.c.name,
                target.c.name,
                User.display_name,
                func.coalesce(qty.c.sku_count, 0),
                func.coalesce(qty.c.total_quantity, 0),
            )
            .join(source, source.c.id == StockTransfer.source_warehouse_id)
            .join(target, target.c.id == StockTransfer.target_warehouse_id)
            .outerjoin(User, User.id == StockTransfer.created_by)
            .outerjoin(qty, qty.c.transfer_id == StockTransfer.id)
            .where(*filters)
            .order_by(StockTransfer.created_at.desc(), StockTransfer.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total
