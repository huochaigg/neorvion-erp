"""采购退货单持久化。不在这里 commit。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.product import ProductSku
from app.models.purchase import PurchaseOrder
from app.models.purchase_return import PurchaseReturn, PurchaseReturnItem
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository
from app.services.purchase_return_state import OCCUPY_STATUSES


class PurchaseReturnRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, return_id: int) -> PurchaseReturn | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReturn)
            .options(
                selectinload(PurchaseReturn.purchase_order),
                selectinload(PurchaseReturn.supplier),
                selectinload(PurchaseReturn.warehouse),
                selectinload(PurchaseReturn.items)
                .selectinload(PurchaseReturnItem.sku)
                .selectinload(ProductSku.product),
                selectinload(PurchaseReturn.items).selectinload(PurchaseReturnItem.purchase_order_item),
            )
            .where(PurchaseReturn.tenant_id == tenant_id, PurchaseReturn.id == return_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, return_id: int) -> PurchaseReturn | None:
        """审核、提交、出库、退款前锁退货单，避免同一张单被处理两次。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReturn)
            .where(PurchaseReturn.tenant_id == tenant_id, PurchaseReturn.id == return_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, order: PurchaseReturn) -> PurchaseReturn:
        self.session.add(order)
        return order

    def add_item(self, item: PurchaseReturnItem) -> PurchaseReturnItem:
        self.session.add(item)
        return item

    def delete_items(self, return_id: int) -> None:
        tenant_id = self.ensure_tenant()
        items = self.session.scalars(
            select(PurchaseReturnItem).where(
                PurchaseReturnItem.tenant_id == tenant_id,
                PurchaseReturnItem.purchase_return_id == return_id,
            )
        ).all()
        for row in items:
            self.session.delete(row)

    def list_items(self, return_id: int) -> list[PurchaseReturnItem]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(PurchaseReturnItem)
            .options(
                selectinload(PurchaseReturnItem.sku).selectinload(ProductSku.product),
                selectinload(PurchaseReturnItem.purchase_order_item),
            )
            .where(
                PurchaseReturnItem.tenant_id == tenant_id,
                PurchaseReturnItem.purchase_return_id == return_id,
            )
            .order_by(PurchaseReturnItem.sku_id.asc(), PurchaseReturnItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def occupied_return_qty(
        self,
        purchase_order_item_ids: list[int],
        *,
        exclude_return_id: int | None = None,
    ) -> dict[int, int]:
        """有效采购退货已占用的退货数量。审核前用申请数量，审核后用批准数量。"""
        if not purchase_order_item_ids:
            return {}
        tenant_id = self.ensure_tenant()
        qty_expr = func.coalesce(
            PurchaseReturnItem.approved_return_quantity,
            PurchaseReturnItem.requested_return_quantity,
        )
        stmt = (
            select(
                PurchaseReturnItem.purchase_order_item_id,
                func.coalesce(func.sum(qty_expr), 0),
            )
            .join(PurchaseReturn, and_(PurchaseReturn.tenant_id == PurchaseReturnItem.tenant_id,
                PurchaseReturn.id == PurchaseReturnItem.purchase_return_id))
            .where(
                PurchaseReturnItem.tenant_id == tenant_id,
                PurchaseReturnItem.purchase_order_item_id.in_(purchase_order_item_ids),
                PurchaseReturn.status.in_(OCCUPY_STATUSES),
            )
            .group_by(PurchaseReturnItem.purchase_order_item_id)
        )
        if exclude_return_id is not None:
            stmt = stmt.where(PurchaseReturn.id != exclude_return_id)
        rows = self.session.execute(stmt).all()
        return {int(item_id): int(total) for item_id, total in rows}

    def occupied_refund_amount(
        self,
        purchase_order_item_ids: list[int],
        *,
        exclude_return_id: int | None = None,
    ) -> dict[int, Decimal]:
        """有效采购退货已占用的退款金额。"""
        if not purchase_order_item_ids:
            return {}
        tenant_id = self.ensure_tenant()
        amount_expr = func.coalesce(
            PurchaseReturnItem.approved_refund_amount,
            PurchaseReturnItem.requested_refund_amount,
            0,
        )
        stmt = (
            select(
                PurchaseReturnItem.purchase_order_item_id,
                func.coalesce(func.sum(amount_expr), 0),
            )
            .join(PurchaseReturn, and_(PurchaseReturn.tenant_id == PurchaseReturnItem.tenant_id,
                PurchaseReturn.id == PurchaseReturnItem.purchase_return_id))
            .where(
                PurchaseReturnItem.tenant_id == tenant_id,
                PurchaseReturnItem.purchase_order_item_id.in_(purchase_order_item_ids),
                PurchaseReturn.status.in_(OCCUPY_STATUSES),
            )
            .group_by(PurchaseReturnItem.purchase_order_item_id)
        )
        if exclude_return_id is not None:
            stmt = stmt.where(PurchaseReturn.id != exclude_return_id)
        rows = self.session.execute(stmt).all()
        return {int(item_id): Decimal(str(total)) for item_id, total in rows}

    def actual_returned_qty(self, purchase_order_item_ids: list[int]) -> dict[int, int]:
        if not purchase_order_item_ids:
            return {}
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                PurchaseReturnItem.purchase_order_item_id,
                func.coalesce(func.sum(PurchaseReturnItem.returned_quantity), 0),
            )
            .join(PurchaseReturn, and_(PurchaseReturn.tenant_id == PurchaseReturnItem.tenant_id,
                PurchaseReturn.id == PurchaseReturnItem.purchase_return_id))
            .where(
                PurchaseReturnItem.tenant_id == tenant_id,
                PurchaseReturnItem.purchase_order_item_id.in_(purchase_order_item_ids),
                PurchaseReturn.status.in_(OCCUPY_STATUSES),
            )
            .group_by(PurchaseReturnItem.purchase_order_item_id)
        )
        rows = self.session.execute(stmt).all()
        return {int(item_id): int(total) for item_id, total in rows}

    def count_by_purchase_order(self, purchase_order_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(PurchaseReturn.id)).where(
            PurchaseReturn.tenant_id == tenant_id,
            PurchaseReturn.purchase_order_id == purchase_order_id,
            PurchaseReturn.status != "DRAFT",
            PurchaseReturn.status != "CANCELLED",
        )
        return int(self.session.scalar(stmt) or 0)

    def list_page(
        self,
        *,
        q: str | None,
        purchase_order_id: int | None,
        supplier_id: int | None,
        warehouse_id: int | None,
        sku_id: int | None,
        status: str | None,
        settlement_type: str | None,
        refund_status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        req_qty = func.coalesce(func.sum(PurchaseReturnItem.requested_return_quantity), 0)
        apr_qty = func.coalesce(func.sum(PurchaseReturnItem.approved_return_quantity), 0)
        ret_qty = func.coalesce(func.sum(PurchaseReturnItem.returned_quantity), 0)
        sku_count = func.count(func.distinct(PurchaseReturnItem.id))
        filters = [PurchaseReturn.tenant_id == tenant_id]
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    PurchaseReturn.purchase_return_no.like(like),
                    PurchaseOrder.order_no.like(like),
                    Supplier.name.like(like),
                )
            )
        if purchase_order_id:
            filters.append(PurchaseReturn.purchase_order_id == purchase_order_id)
        if supplier_id:
            filters.append(PurchaseReturn.supplier_id == supplier_id)
        if warehouse_id:
            filters.append(PurchaseReturn.warehouse_id == warehouse_id)
        if status:
            filters.append(PurchaseReturn.status == status)
        if settlement_type:
            filters.append(PurchaseReturn.settlement_type == settlement_type)
        if refund_status:
            filters.append(PurchaseReturn.refund_status == refund_status)
        if created_from:
            filters.append(PurchaseReturn.created_at >= created_from)
        if created_to:
            filters.append(PurchaseReturn.created_at <= created_to)
        if sku_id:
            sku_exists = (
                select(PurchaseReturnItem.id)
                .where(
                    PurchaseReturnItem.purchase_return_id == PurchaseReturn.id,
                    PurchaseReturnItem.tenant_id == tenant_id,
                    PurchaseReturnItem.sku_id == sku_id,
                )
                .exists()
            )
            filters.append(sku_exists)

        base = (
            select(PurchaseReturn)
            .join(PurchaseOrder, and_(PurchaseOrder.tenant_id == PurchaseReturn.tenant_id,
                PurchaseOrder.id == PurchaseReturn.purchase_order_id))
            .join(Supplier, and_(Supplier.tenant_id == PurchaseReturn.tenant_id,
                Supplier.id == PurchaseReturn.supplier_id))
            .join(Warehouse, and_(Warehouse.tenant_id == PurchaseReturn.tenant_id,
                Warehouse.id == PurchaseReturn.warehouse_id))
            .outerjoin(
                PurchaseReturnItem,
                PurchaseReturnItem.purchase_return_id == PurchaseReturn.id,
            )
            .where(*filters)
            .group_by(PurchaseReturn.id, PurchaseOrder.id, Supplier.id, Warehouse.id)
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = int(self.session.scalar(count_stmt) or 0)
        stmt = (
            select(
                PurchaseReturn,
                PurchaseOrder.order_no,
                Supplier.name,
                Warehouse.name,
                sku_count,
                req_qty,
                apr_qty,
                ret_qty,
            )
            .join(PurchaseOrder, and_(PurchaseOrder.tenant_id == PurchaseReturn.tenant_id,
                PurchaseOrder.id == PurchaseReturn.purchase_order_id))
            .join(Supplier, and_(Supplier.tenant_id == PurchaseReturn.tenant_id,
                Supplier.id == PurchaseReturn.supplier_id))
            .join(Warehouse, and_(Warehouse.tenant_id == PurchaseReturn.tenant_id,
                Warehouse.id == PurchaseReturn.warehouse_id))
            .outerjoin(
                PurchaseReturnItem,
                PurchaseReturnItem.purchase_return_id == PurchaseReturn.id,
            )
            .where(*filters)
            .group_by(PurchaseReturn.id, PurchaseOrder.id, Supplier.id, Warehouse.id)
            .order_by(PurchaseReturn.created_at.desc(), PurchaseReturn.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total
