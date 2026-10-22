"""售后单持久化。不在这里 commit。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.after_sale import AfterSaleItem, AfterSaleOrder, AfterSaleStatus
from app.models.customer import Customer
from app.models.identity import IdentityNameSnapshot
from app.models.product import ProductSku
from app.models.sales_order import SalesOrder
from app.repositories.base import BaseRepository

# 未拒绝、未取消的售后占用可退数量，避免两张单同时把同一批货退走。
_OCCUPY_STATUSES = (
    AfterSaleStatus.PENDING_APPROVAL.value,
    AfterSaleStatus.WAITING_RETURN.value,
    AfterSaleStatus.WAITING_REFUND.value,
    AfterSaleStatus.COMPLETED.value,
)


class AfterSaleRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, after_sale_id: int) -> AfterSaleOrder | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(AfterSaleOrder)
            .options(
                selectinload(AfterSaleOrder.sales_order),
                selectinload(AfterSaleOrder.customer),
                selectinload(AfterSaleOrder.items)
                .selectinload(AfterSaleItem.sku)
                .selectinload(ProductSku.product),
                selectinload(AfterSaleOrder.items).selectinload(AfterSaleItem.sales_order_item),
            )
            .where(AfterSaleOrder.tenant_id == tenant_id, AfterSaleOrder.id == after_sale_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, after_sale_id: int) -> AfterSaleOrder | None:
        """审核、取消、退款前锁售后单，避免同一张单被处理两次。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(AfterSaleOrder)
            .where(AfterSaleOrder.tenant_id == tenant_id, AfterSaleOrder.id == after_sale_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, order: AfterSaleOrder) -> AfterSaleOrder:
        self.session.add(order)
        return order

    def add_item(self, item: AfterSaleItem) -> AfterSaleItem:
        self.session.add(item)
        return item

    def list_items(self, after_sale_id: int) -> list[AfterSaleItem]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(AfterSaleItem)
            .options(selectinload(AfterSaleItem.sku).selectinload(ProductSku.product))
            .where(
                AfterSaleItem.tenant_id == tenant_id,
                AfterSaleItem.after_sale_order_id == after_sale_id,
            )
            .order_by(AfterSaleItem.sku_id.asc(), AfterSaleItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def occupied_return_qty(
        self,
        sales_order_item_ids: list[int],
        *,
        exclude_after_sale_id: int | None = None,
    ) -> dict[int, int]:
        """有效售后已占用的退货数量。审核前用申请数量，审核后用批准数量。"""
        if not sales_order_item_ids:
            return {}
        tenant_id = self.ensure_tenant()
        qty_expr = func.coalesce(
            AfterSaleItem.approved_return_quantity,
            AfterSaleItem.return_quantity,
        )
        stmt = (
            select(AfterSaleItem.sales_order_item_id, func.coalesce(func.sum(qty_expr), 0))
            .join(AfterSaleOrder, and_(AfterSaleOrder.tenant_id == AfterSaleItem.tenant_id,
                AfterSaleOrder.id == AfterSaleItem.after_sale_order_id))
            .where(
                AfterSaleItem.tenant_id == tenant_id,
                AfterSaleItem.sales_order_item_id.in_(sales_order_item_ids),
                AfterSaleOrder.status.in_(_OCCUPY_STATUSES),
            )
            .group_by(AfterSaleItem.sales_order_item_id)
        )
        if exclude_after_sale_id is not None:
            stmt = stmt.where(AfterSaleOrder.id != exclude_after_sale_id)
        rows = self.session.execute(stmt).all()
        return {int(item_id): int(total) for item_id, total in rows}

    def occupied_refund_amount(
        self,
        sales_order_item_ids: list[int],
        *,
        exclude_after_sale_id: int | None = None,
    ) -> dict[int, Decimal]:
        """有效售后已占用的退款金额。"""
        if not sales_order_item_ids:
            return {}
        tenant_id = self.ensure_tenant()
        amount_expr = func.coalesce(
            AfterSaleItem.approved_refund_amount,
            AfterSaleItem.requested_refund_amount,
        )
        stmt = (
            select(
                AfterSaleItem.sales_order_item_id,
                func.coalesce(func.sum(amount_expr), 0),
            )
            .join(AfterSaleOrder, and_(AfterSaleOrder.tenant_id == AfterSaleItem.tenant_id,
                AfterSaleOrder.id == AfterSaleItem.after_sale_order_id))
            .where(
                AfterSaleItem.tenant_id == tenant_id,
                AfterSaleItem.sales_order_item_id.in_(sales_order_item_ids),
                AfterSaleOrder.status.in_(_OCCUPY_STATUSES),
            )
            .group_by(AfterSaleItem.sales_order_item_id)
        )
        if exclude_after_sale_id is not None:
            stmt = stmt.where(AfterSaleOrder.id != exclude_after_sale_id)
        rows = self.session.execute(stmt).all()
        return {int(item_id): Decimal(str(total)) for item_id, total in rows}

    def list_page(
        self,
        *,
        q: str | None,
        sales_order_id: int | None,
        customer_id: int | None,
        sku_code: str | None,
        after_sale_type: str | None,
        status: str | None,
        refund_status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        return_qty = func.coalesce(func.sum(AfterSaleItem.return_quantity), 0)
        filters = [AfterSaleOrder.tenant_id == tenant_id]
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    AfterSaleOrder.after_sale_no.like(like),
                    SalesOrder.order_no.like(like),
                    Customer.name.like(like),
                )
            )
        if sales_order_id:
            filters.append(AfterSaleOrder.sales_order_id == sales_order_id)
        if customer_id:
            filters.append(AfterSaleOrder.customer_id == customer_id)
        if after_sale_type:
            filters.append(AfterSaleOrder.type == after_sale_type)
        if status:
            filters.append(AfterSaleOrder.status == status)
        if refund_status:
            filters.append(AfterSaleOrder.refund_status == refund_status)
        if created_from:
            filters.append(AfterSaleOrder.created_at >= created_from)
        if created_to:
            filters.append(AfterSaleOrder.created_at <= created_to)
        if sku_code:
            sku_exists = (
                select(AfterSaleItem.id)
                .join(ProductSku, and_(ProductSku.tenant_id == AfterSaleItem.tenant_id,
                    ProductSku.id == AfterSaleItem.sku_id))
                .where(
                    AfterSaleItem.after_sale_order_id == AfterSaleOrder.id,
                    AfterSaleItem.tenant_id == tenant_id,
                    ProductSku.sku_code.like(f"%{sku_code}%"),
                )
                .exists()
            )
            filters.append(sku_exists)

        base = (
            select(AfterSaleOrder)
            .join(SalesOrder, and_(SalesOrder.tenant_id == AfterSaleOrder.tenant_id,
                SalesOrder.id == AfterSaleOrder.sales_order_id))
            .join(Customer, and_(Customer.tenant_id == AfterSaleOrder.tenant_id,
                Customer.id == AfterSaleOrder.customer_id))
            .outerjoin(AfterSaleItem, AfterSaleItem.after_sale_order_id == AfterSaleOrder.id)
            .outerjoin(
                IdentityNameSnapshot,
                IdentityNameSnapshot.user_id == AfterSaleOrder.requested_by,
            )
            .where(*filters)
            .group_by(
                AfterSaleOrder.id,
                SalesOrder.id,
                Customer.id,
                IdentityNameSnapshot.user_id,
            )
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = int(self.session.scalar(count_stmt) or 0)
        stmt = (
            select(
                AfterSaleOrder,
                SalesOrder.order_no,
                Customer.name,
                IdentityNameSnapshot.display_name,
                return_qty,
            )
            .join(SalesOrder, and_(SalesOrder.tenant_id == AfterSaleOrder.tenant_id,
                SalesOrder.id == AfterSaleOrder.sales_order_id))
            .join(Customer, and_(Customer.tenant_id == AfterSaleOrder.tenant_id,
                Customer.id == AfterSaleOrder.customer_id))
            .outerjoin(AfterSaleItem, AfterSaleItem.after_sale_order_id == AfterSaleOrder.id)
            .outerjoin(
                IdentityNameSnapshot,
                IdentityNameSnapshot.user_id == AfterSaleOrder.requested_by,
            )
            .where(*filters)
            .group_by(
                AfterSaleOrder.id,
                SalesOrder.id,
                Customer.id,
                IdentityNameSnapshot.user_id,
            )
            .order_by(AfterSaleOrder.created_at.desc(), AfterSaleOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total
