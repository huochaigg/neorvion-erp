"""采购退货出库单持久化。不在这里 commit。"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.product import ProductSku
from app.models.purchase import PurchaseOrder
from app.models.purchase_return import PurchaseReturn
from app.models.purchase_return_outbound import PurchaseReturnOutbound, PurchaseReturnOutboundItem
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository


class PurchaseReturnOutboundRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, outbound_id: int) -> PurchaseReturnOutbound | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReturnOutbound)
            .options(
                selectinload(PurchaseReturnOutbound.purchase_return).selectinload(PurchaseReturn.purchase_order),
                selectinload(PurchaseReturnOutbound.purchase_return).selectinload(PurchaseReturn.supplier),
                selectinload(PurchaseReturnOutbound.warehouse),
                selectinload(PurchaseReturnOutbound.items)
                .selectinload(PurchaseReturnOutboundItem.sku)
                .selectinload(ProductSku.product),
                selectinload(PurchaseReturnOutbound.items).selectinload(
                    PurchaseReturnOutboundItem.purchase_return_item
                ),
            )
            .where(
                PurchaseReturnOutbound.tenant_id == tenant_id,
                PurchaseReturnOutbound.id == outbound_id,
            )
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, outbound_id: int) -> PurchaseReturnOutbound | None:
        """确认出库前锁出库单，避免同一张单被确认两次导致重复扣库存。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReturnOutbound)
            .where(
                PurchaseReturnOutbound.tenant_id == tenant_id,
                PurchaseReturnOutbound.id == outbound_id,
            )
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def list_by_return(self, purchase_return_id: int) -> list[PurchaseReturnOutbound]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReturnOutbound)
            .options(
                selectinload(PurchaseReturnOutbound.items)
                .selectinload(PurchaseReturnOutboundItem.sku)
                .selectinload(ProductSku.product),
            )
            .where(
                PurchaseReturnOutbound.tenant_id == tenant_id,
                PurchaseReturnOutbound.purchase_return_id == purchase_return_id,
            )
            .order_by(PurchaseReturnOutbound.created_at.desc(), PurchaseReturnOutbound.id.desc())
        )
        return list(self.session.scalars(stmt).all())

    def add(self, outbound: PurchaseReturnOutbound) -> PurchaseReturnOutbound:
        self.session.add(outbound)
        return outbound

    def add_item(self, item: PurchaseReturnOutboundItem) -> PurchaseReturnOutboundItem:
        self.session.add(item)
        return item

    def list_items(self, outbound_id: int) -> list[PurchaseReturnOutboundItem]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReturnOutboundItem)
            .options(
                selectinload(PurchaseReturnOutboundItem.sku).selectinload(ProductSku.product),
                selectinload(PurchaseReturnOutboundItem.purchase_return_item),
            )
            .where(
                PurchaseReturnOutboundItem.tenant_id == tenant_id,
                PurchaseReturnOutboundItem.purchase_return_outbound_id == outbound_id,
            )
            .order_by(PurchaseReturnOutboundItem.sku_id.asc(), PurchaseReturnOutboundItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_page(
        self,
        *,
        q: str | None,
        purchase_return_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        total_qty = func.coalesce(func.sum(PurchaseReturnOutboundItem.quantity), 0)
        filters = [PurchaseReturnOutbound.tenant_id == tenant_id]
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    PurchaseReturnOutbound.outbound_no.like(like),
                    PurchaseReturn.purchase_return_no.like(like),
                    PurchaseOrder.order_no.like(like),
                )
            )
        if purchase_return_id:
            filters.append(PurchaseReturnOutbound.purchase_return_id == purchase_return_id)
        if status:
            filters.append(PurchaseReturnOutbound.status == status)
        if created_from:
            filters.append(PurchaseReturnOutbound.created_at >= created_from)
        if created_to:
            filters.append(PurchaseReturnOutbound.created_at <= created_to)

        base = (
            select(PurchaseReturnOutbound)
            .join(PurchaseReturn, PurchaseReturn.id == PurchaseReturnOutbound.purchase_return_id)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseReturn.purchase_order_id)
            .join(Supplier, Supplier.id == PurchaseReturn.supplier_id)
            .join(Warehouse, Warehouse.id == PurchaseReturnOutbound.warehouse_id)
            .outerjoin(
                PurchaseReturnOutboundItem,
                PurchaseReturnOutboundItem.purchase_return_outbound_id == PurchaseReturnOutbound.id,
            )
            .where(*filters)
            .group_by(
                PurchaseReturnOutbound.id,
                PurchaseReturn.id,
                PurchaseOrder.id,
                Supplier.id,
                Warehouse.id,
            )
        )
        total = int(self.session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        stmt = (
            select(
                PurchaseReturnOutbound,
                PurchaseReturn.purchase_return_no,
                PurchaseOrder.order_no,
                Supplier.name,
                Warehouse.name,
                total_qty,
            )
            .join(PurchaseReturn, PurchaseReturn.id == PurchaseReturnOutbound.purchase_return_id)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseReturn.purchase_order_id)
            .join(Supplier, Supplier.id == PurchaseReturn.supplier_id)
            .join(Warehouse, Warehouse.id == PurchaseReturnOutbound.warehouse_id)
            .outerjoin(
                PurchaseReturnOutboundItem,
                PurchaseReturnOutboundItem.purchase_return_outbound_id == PurchaseReturnOutbound.id,
            )
            .where(*filters)
            .group_by(
                PurchaseReturnOutbound.id,
                PurchaseReturn.id,
                PurchaseOrder.id,
                Supplier.id,
                Warehouse.id,
            )
            .order_by(PurchaseReturnOutbound.created_at.desc(), PurchaseReturnOutbound.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total
