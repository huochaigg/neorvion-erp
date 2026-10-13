"""采购收货单持久化。不在这里 commit。"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.product import ProductSku
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.purchase_receipt import PurchaseReceipt, PurchaseReceiptItem
from app.models.supplier import Supplier
from app.models.user import User
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository


class PurchaseReceiptRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, receipt_id: int) -> PurchaseReceipt | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReceipt)
            .options(
                selectinload(PurchaseReceipt.purchase_order).selectinload(PurchaseOrder.supplier),
                selectinload(PurchaseReceipt.purchase_order).selectinload(PurchaseOrder.warehouse),
                selectinload(PurchaseReceipt.items)
                .selectinload(PurchaseReceiptItem.sku)
                .selectinload(ProductSku.product),
                selectinload(PurchaseReceipt.items).selectinload(
                    PurchaseReceiptItem.purchase_order_item
                ),
            )
            .where(PurchaseReceipt.tenant_id == tenant_id, PurchaseReceipt.id == receipt_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, receipt_id: int) -> PurchaseReceipt | None:
        """确认和取消前锁收货单，避免同一张单被确认两次。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReceipt)
            .where(PurchaseReceipt.tenant_id == tenant_id, PurchaseReceipt.id == receipt_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, receipt: PurchaseReceipt) -> PurchaseReceipt:
        self.session.add(receipt)
        return receipt

    def delete_items(self, receipt_id: int) -> None:
        tenant_id = self.ensure_tenant()
        rows = self.session.scalars(
            select(PurchaseReceiptItem).where(
                PurchaseReceiptItem.tenant_id == tenant_id,
                PurchaseReceiptItem.purchase_receipt_id == receipt_id,
            )
        ).all()
        for row in rows:
            self.session.delete(row)

    def list_po_items_for_update(self, purchase_order_id: int) -> list[PurchaseOrderItem]:
        """按 sku_id 升序锁采购明细。两张收货单并发时以相同顺序等待这些行。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseOrderItem)
            .where(
                PurchaseOrderItem.tenant_id == tenant_id,
                PurchaseOrderItem.purchase_order_id == purchase_order_id,
            )
            .order_by(PurchaseOrderItem.sku_id.asc(), PurchaseOrderItem.id.asc())
            .with_for_update()
        )
        return list(self.session.scalars(stmt).all())

    def list_page(
        self,
        *,
        q: str | None,
        purchase_order_id: int | None,
        supplier_id: int | None,
        warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        filters = [PurchaseReceipt.tenant_id == tenant_id]
        if q:
            filters.append(PurchaseReceipt.receipt_no.like(f"%{q}%"))
        if purchase_order_id:
            filters.append(PurchaseReceipt.purchase_order_id == purchase_order_id)
        if warehouse_id:
            filters.append(PurchaseReceipt.warehouse_id == warehouse_id)
        if status:
            filters.append(PurchaseReceipt.status == status)
        if created_from is not None:
            filters.append(PurchaseReceipt.created_at >= created_from)
        if created_to is not None:
            filters.append(PurchaseReceipt.created_at <= created_to)
        item_qty = (
            select(
                PurchaseReceiptItem.purchase_receipt_id.label("receipt_id"),
                func.count(PurchaseReceiptItem.id).label("sku_count"),
                func.coalesce(func.sum(PurchaseReceiptItem.received_quantity), 0).label(
                    "total_received"
                ),
            )
            .where(PurchaseReceiptItem.tenant_id == tenant_id)
            .group_by(PurchaseReceiptItem.purchase_receipt_id)
            .subquery()
        )
        stmt = (
            select(
                PurchaseReceipt,
                PurchaseOrder.order_no,
                Supplier.name,
                Warehouse.name,
                User.display_name,
                func.coalesce(item_qty.c.sku_count, 0),
                func.coalesce(item_qty.c.total_received, 0),
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseReceipt.purchase_order_id)
            .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
            .join(Warehouse, Warehouse.id == PurchaseReceipt.warehouse_id)
            .outerjoin(User, User.id == PurchaseReceipt.received_by)
            .outerjoin(item_qty, item_qty.c.receipt_id == PurchaseReceipt.id)
            .where(*filters)
        )
        if supplier_id:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
        total = int(self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.session.execute(
            stmt.order_by(PurchaseReceipt.created_at.desc(), PurchaseReceipt.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(rows), total
