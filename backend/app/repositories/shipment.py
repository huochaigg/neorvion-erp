"""物流单持久化。不在这里 commit。"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.carrier import Carrier
from app.models.customer import Customer
from app.models.outbound import OutboundOrder, OutboundOrderItem
from app.models.product import ProductSku
from app.models.sales_order import SalesOrder
from app.models.shipment import Shipment, ShipmentItem, ShipmentStatus
from app.repositories.base import BaseRepository

_ACTIVE_SHIP = (
    ShipmentStatus.DRAFT.value,
    ShipmentStatus.SHIPPED.value,
    ShipmentStatus.IN_TRANSIT.value,
    ShipmentStatus.DELIVERED.value,
)
_CONFIRMED_SHIP = (
    ShipmentStatus.SHIPPED.value,
    ShipmentStatus.IN_TRANSIT.value,
    ShipmentStatus.DELIVERED.value,
)


class ShipmentRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, shipment_id: int) -> Shipment | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Shipment)
            .options(
                selectinload(Shipment.sales_order).selectinload(SalesOrder.customer),
                selectinload(Shipment.sales_order).selectinload(SalesOrder.warehouse),
                selectinload(Shipment.outbound_order),
                selectinload(Shipment.carrier),
                selectinload(Shipment.items)
                .selectinload(ShipmentItem.sku)
                .selectinload(ProductSku.product),
                selectinload(Shipment.tracking_events),
            )
            .where(Shipment.tenant_id == tenant_id, Shipment.id == shipment_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, shipment_id: int) -> Shipment | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Shipment)
            .where(Shipment.tenant_id == tenant_id, Shipment.id == shipment_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, shipment: Shipment) -> Shipment:
        self.session.add(shipment)
        return shipment

    def list_items(self, shipment_id: int) -> list[ShipmentItem]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(ShipmentItem)
            .where(
                ShipmentItem.tenant_id == tenant_id,
                ShipmentItem.shipment_id == shipment_id,
            )
            .order_by(ShipmentItem.sku_id.asc(), ShipmentItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def delete_items(self, shipment_id: int) -> None:
        tenant_id = self.ensure_tenant()
        rows = self.list_items(shipment_id)
        for row in rows:
            if row.tenant_id == tenant_id:
                self.session.delete(row)

    def list_outbound_items_for_update(self, outbound_id: int) -> list[OutboundOrderItem]:
        """按 sku_id 升序锁出库明细，避免多张物流单交叉加锁。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(OutboundOrderItem)
            .where(
                OutboundOrderItem.tenant_id == tenant_id,
                OutboundOrderItem.outbound_order_id == outbound_id,
            )
            .order_by(OutboundOrderItem.sku_id.asc(), OutboundOrderItem.id.asc())
            .with_for_update()
        )
        return list(self.session.scalars(stmt).all())

    def allocated_by_outbound_item(
        self,
        outbound_id: int,
        *,
        confirmed_only: bool = False,
        exclude_shipment_id: int | None = None,
    ) -> dict[int, int]:
        """每个出库明细已经被物流单占用的数量。"""
        tenant_id = self.ensure_tenant()
        statuses = _CONFIRMED_SHIP if confirmed_only else _ACTIVE_SHIP
        filters = [
            Shipment.tenant_id == tenant_id,
            Shipment.outbound_order_id == outbound_id,
            Shipment.status.in_(statuses),
            ShipmentItem.tenant_id == tenant_id,
        ]
        if exclude_shipment_id is not None:
            filters.append(Shipment.id != exclude_shipment_id)
        stmt = (
            select(
                ShipmentItem.outbound_order_item_id,
                func.coalesce(func.sum(ShipmentItem.quantity), 0),
            )
            .join(Shipment, Shipment.id == ShipmentItem.shipment_id)
            .where(*filters)
            .group_by(ShipmentItem.outbound_order_item_id)
        )
        return {int(item_id): int(qty) for item_id, qty in self.session.execute(stmt).all()}

    def list_for_sales_order(self, sales_order_id: int) -> list[Shipment]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Shipment)
            .options(selectinload(Shipment.carrier), selectinload(Shipment.items))
            .where(
                Shipment.tenant_id == tenant_id,
                Shipment.sales_order_id == sales_order_id,
            )
            .order_by(Shipment.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_for_outbound(self, outbound_id: int) -> list[Shipment]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Shipment)
            .options(selectinload(Shipment.carrier), selectinload(Shipment.items))
            .where(
                Shipment.tenant_id == tenant_id,
                Shipment.outbound_order_id == outbound_id,
            )
            .order_by(Shipment.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_page(
        self,
        *,
        q: str | None,
        sales_order_id: int | None,
        outbound_order_id: int | None,
        carrier_id: int | None,
        customer_id: int | None,
        status: str | None,
        shipped_from: datetime | None,
        shipped_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        filters = [Shipment.tenant_id == tenant_id]
        if sales_order_id:
            filters.append(Shipment.sales_order_id == sales_order_id)
        if outbound_order_id:
            filters.append(Shipment.outbound_order_id == outbound_order_id)
        if carrier_id:
            filters.append(Shipment.carrier_id == carrier_id)
        if customer_id:
            filters.append(SalesOrder.customer_id == customer_id)
        if status:
            filters.append(Shipment.status == status)
        if shipped_from:
            filters.append(Shipment.shipped_at >= shipped_from)
        if shipped_to:
            filters.append(Shipment.shipped_at <= shipped_to)
        if q:
            pattern = f"%{q}%"
            filters.append(
                or_(
                    Shipment.shipment_no.like(pattern),
                    Shipment.tracking_no.like(pattern),
                    SalesOrder.order_no.like(pattern),
                    OutboundOrder.outbound_no.like(pattern),
                )
            )
        qty = (
            select(
                ShipmentItem.shipment_id.label("shipment_id"),
                func.count(ShipmentItem.id).label("sku_count"),
                func.coalesce(func.sum(ShipmentItem.quantity), 0).label("total_qty"),
            )
            .where(ShipmentItem.tenant_id == tenant_id)
            .group_by(ShipmentItem.shipment_id)
            .subquery()
        )
        stmt = (
            select(
                Shipment,
                SalesOrder.order_no,
                OutboundOrder.outbound_no,
                Customer.name,
                Carrier.name,
                func.coalesce(qty.c.sku_count, 0),
                func.coalesce(qty.c.total_qty, 0),
            )
            .join(SalesOrder, SalesOrder.id == Shipment.sales_order_id)
            .join(OutboundOrder, OutboundOrder.id == Shipment.outbound_order_id)
            .join(Customer, Customer.id == SalesOrder.customer_id)
            .join(Carrier, Carrier.id == Shipment.carrier_id)
            .outerjoin(qty, qty.c.shipment_id == Shipment.id)
            .where(*filters)
        )
        total = int(self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.session.execute(
            stmt.order_by(Shipment.created_at.desc(), Shipment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), total
