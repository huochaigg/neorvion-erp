"""销售出库单持久化。不在这里 commit。"""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.customer import Customer
from app.models.outbound import (
    OutboundOrder,
    OutboundOrderItem,
    OutboundOrderStatus,
    OutboundPick,
    OutboundPickLine,
)
from app.models.product import ProductSku
from app.models.sales_order import SalesOrder, SalesOrderItem
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository

_OPEN = (
    OutboundOrderStatus.PENDING_PICKING.value,
    OutboundOrderStatus.PICKED.value,
)


class OutboundOrderRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, outbound_id: int) -> OutboundOrder | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(OutboundOrder)
            .options(
                selectinload(OutboundOrder.sales_order).selectinload(SalesOrder.customer),
                selectinload(OutboundOrder.sales_order).selectinload(SalesOrder.warehouse),
                selectinload(OutboundOrder.items)
                .selectinload(OutboundOrderItem.sku)
                .selectinload(ProductSku.product),
            )
            .where(OutboundOrder.tenant_id == tenant_id, OutboundOrder.id == outbound_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, outbound_id: int) -> OutboundOrder | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(OutboundOrder)
            .where(OutboundOrder.tenant_id == tenant_id, OutboundOrder.id == outbound_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, order: OutboundOrder) -> OutboundOrder:
        self.session.add(order)
        return order

    def list_items(self, outbound_id: int) -> list[OutboundOrderItem]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(OutboundOrderItem)
            .where(
                OutboundOrderItem.tenant_id == tenant_id,
                OutboundOrderItem.outbound_order_id == outbound_id,
            )
            .order_by(OutboundOrderItem.sku_id.asc(), OutboundOrderItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_sales_items_for_update(self, sales_order_id: int) -> list[SalesOrderItem]:
        """按 sku_id 升序锁订单明细，和库存行使用同一把顺序。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(SalesOrderItem)
            .where(
                SalesOrderItem.tenant_id == tenant_id,
                SalesOrderItem.sales_order_id == sales_order_id,
            )
            .order_by(SalesOrderItem.sku_id.asc(), SalesOrderItem.id.asc())
            .with_for_update()
        )
        return list(self.session.scalars(stmt).all())

    def open_planned_by_item(self, sales_order_id: int) -> dict[int, int]:
        """未完成出库单已经占住的计划数量。确认后的不再占用剩余预占。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                OutboundOrderItem.sales_order_item_id,
                func.coalesce(func.sum(OutboundOrderItem.planned_quantity), 0),
            )
            .join(OutboundOrder, OutboundOrder.id == OutboundOrderItem.outbound_order_id)
            .where(
                OutboundOrder.tenant_id == tenant_id,
                OutboundOrder.sales_order_id == sales_order_id,
                OutboundOrder.status.in_(_OPEN),
            )
            .group_by(OutboundOrderItem.sales_order_item_id)
        )
        return {int(item_id): int(qty) for item_id, qty in self.session.execute(stmt).all()}

    def has_active(self, sales_order_id: int) -> bool:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(OutboundOrder.id)).where(
            OutboundOrder.tenant_id == tenant_id,
            OutboundOrder.sales_order_id == sales_order_id,
            OutboundOrder.status != OutboundOrderStatus.CANCELLED.value,
        )
        return int(self.session.scalar(stmt) or 0) > 0

    def cancel_open_for_sales_order(self, sales_order_id: int) -> None:
        """整单取消时作废尚未出库的拣货任务。已确认的出库单不能从这里改。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            update(OutboundOrder)
            .where(
                OutboundOrder.tenant_id == tenant_id,
                OutboundOrder.sales_order_id == sales_order_id,
                OutboundOrder.status.in_(_OPEN),
            )
            .values(status=OutboundOrderStatus.CANCELLED.value, updated_at=func.now())
        )
        self.session.execute(stmt)

    def list_page(
        self,
        *,
        q: str | None,
        sales_order_id: int | None,
        warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        filters = [OutboundOrder.tenant_id == tenant_id]
        if q:
            filters.append(OutboundOrder.outbound_no.like(f"%{q}%"))
        if sales_order_id:
            filters.append(OutboundOrder.sales_order_id == sales_order_id)
        if warehouse_id:
            filters.append(OutboundOrder.warehouse_id == warehouse_id)
        if status:
            filters.append(OutboundOrder.status == status)
        if created_from is not None:
            filters.append(OutboundOrder.created_at >= created_from)
        if created_to is not None:
            filters.append(OutboundOrder.created_at <= created_to)
        qty = (
            select(
                OutboundOrderItem.outbound_order_id.label("outbound_id"),
                func.count(OutboundOrderItem.id).label("sku_count"),
                func.coalesce(func.sum(OutboundOrderItem.planned_quantity), 0).label("planned"),
                func.coalesce(func.sum(OutboundOrderItem.picked_quantity), 0).label("picked"),
                func.coalesce(func.sum(OutboundOrderItem.outbound_quantity), 0).label("outbound"),
            )
            .where(OutboundOrderItem.tenant_id == tenant_id)
            .group_by(OutboundOrderItem.outbound_order_id)
            .subquery()
        )
        stmt = (
            select(
                OutboundOrder,
                SalesOrder.order_no,
                Customer.name,
                Warehouse.name,
                func.coalesce(qty.c.sku_count, 0),
                func.coalesce(qty.c.planned, 0),
                func.coalesce(qty.c.picked, 0),
                func.coalesce(qty.c.outbound, 0),
            )
            .join(SalesOrder, SalesOrder.id == OutboundOrder.sales_order_id)
            .join(Customer, Customer.id == SalesOrder.customer_id)
            .join(Warehouse, Warehouse.id == OutboundOrder.warehouse_id)
            .outerjoin(qty, qty.c.outbound_id == OutboundOrder.id)
            .where(*filters)
        )
        total = int(self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.session.execute(
            stmt.order_by(OutboundOrder.created_at.desc(), OutboundOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), total

    def list_for_sales_order(self, sales_order_id: int) -> list[OutboundOrder]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(OutboundOrder)
            .where(
                OutboundOrder.tenant_id == tenant_id,
                OutboundOrder.sales_order_id == sales_order_id,
            )
            .order_by(OutboundOrder.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_picks(self, outbound_id: int) -> list[OutboundPick]:
        tenant_id = self.ensure_tenant()
        stmt = self._pick_stmt().where(
            OutboundPick.tenant_id == tenant_id,
            OutboundPick.outbound_order_id == outbound_id,
        )
        return list(self.session.scalars(stmt).all())

    def list_picks_for_sales_order(self, sales_order_id: int) -> list[OutboundPick]:
        tenant_id = self.ensure_tenant()
        stmt = (
            self._pick_stmt()
            .join(OutboundOrder, OutboundOrder.id == OutboundPick.outbound_order_id)
            .where(
                OutboundPick.tenant_id == tenant_id,
                OutboundOrder.tenant_id == tenant_id,
                OutboundOrder.sales_order_id == sales_order_id,
            )
        )
        return list(self.session.scalars(stmt).unique().all())

    def _pick_stmt(self):
        return (
            select(OutboundPick)
            .options(
                selectinload(OutboundPick.outbound_order),
                selectinload(OutboundPick.lines)
                .selectinload(OutboundPickLine.sku)
                .selectinload(ProductSku.product),
            )
            .order_by(OutboundPick.id.asc())
        )
