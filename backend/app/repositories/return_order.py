"""退货单持久化。不在这里 commit。"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.after_sale import AfterSaleOrder
from app.models.customer import Customer
from app.models.product import ProductSku
from app.models.return_order import ReturnOrder, ReturnOrderItem
from app.models.sales_order import SalesOrder
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository


class ReturnOrderRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, return_id: int) -> ReturnOrder | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(ReturnOrder)
            .options(
                selectinload(ReturnOrder.after_sale_order).selectinload(AfterSaleOrder.customer),
                selectinload(ReturnOrder.sales_order),
                selectinload(ReturnOrder.warehouse),
                selectinload(ReturnOrder.items)
                .selectinload(ReturnOrderItem.sku)
                .selectinload(ProductSku.product),
            )
            .where(ReturnOrder.tenant_id == tenant_id, ReturnOrder.id == return_id)
        )
        return self.session.scalars(stmt).first()

    def get_by_after_sale(self, after_sale_id: int) -> ReturnOrder | None:
        tenant_id = self.ensure_tenant()
        stmt = select(ReturnOrder).where(
            ReturnOrder.tenant_id == tenant_id,
            ReturnOrder.after_sale_order_id == after_sale_id,
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, return_id: int) -> ReturnOrder | None:
        """收货和入库前锁退货单，避免同一张单被入库两次。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(ReturnOrder)
            .where(ReturnOrder.tenant_id == tenant_id, ReturnOrder.id == return_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def add(self, order: ReturnOrder) -> ReturnOrder:
        self.session.add(order)
        return order

    def add_item(self, item: ReturnOrderItem) -> ReturnOrderItem:
        self.session.add(item)
        return item

    def list_items(self, return_id: int) -> list[ReturnOrderItem]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(ReturnOrderItem)
            .options(selectinload(ReturnOrderItem.sku).selectinload(ProductSku.product))
            .where(
                ReturnOrderItem.tenant_id == tenant_id,
                ReturnOrderItem.return_order_id == return_id,
            )
            .order_by(ReturnOrderItem.sku_id.asc(), ReturnOrderItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get_item(self, return_id: int, item_id: int) -> ReturnOrderItem | None:
        tenant_id = self.ensure_tenant()
        stmt = select(ReturnOrderItem).where(
            ReturnOrderItem.tenant_id == tenant_id,
            ReturnOrderItem.return_order_id == return_id,
            ReturnOrderItem.id == item_id,
        )
        return self.session.scalars(stmt).first()

    def count_by_warehouse(self, warehouse_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(ReturnOrder.id)).where(
            ReturnOrder.tenant_id == tenant_id,
            ReturnOrder.warehouse_id == warehouse_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def list_page(
        self,
        *,
        q: str | None,
        after_sale_id: int | None,
        sales_order_id: int | None,
        warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        tenant_id = self.ensure_tenant()
        expected = func.coalesce(func.sum(ReturnOrderItem.expected_quantity), 0)
        received = func.coalesce(func.sum(ReturnOrderItem.received_quantity), 0)
        inbound = func.coalesce(func.sum(ReturnOrderItem.inbound_quantity), 0)
        filters = [ReturnOrder.tenant_id == tenant_id]
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    ReturnOrder.return_no.like(like),
                    AfterSaleOrder.after_sale_no.like(like),
                    SalesOrder.order_no.like(like),
                )
            )
        if after_sale_id:
            filters.append(ReturnOrder.after_sale_order_id == after_sale_id)
        if sales_order_id:
            filters.append(ReturnOrder.sales_order_id == sales_order_id)
        if warehouse_id:
            filters.append(ReturnOrder.warehouse_id == warehouse_id)
        if status:
            filters.append(ReturnOrder.status == status)
        if created_from:
            filters.append(ReturnOrder.created_at >= created_from)
        if created_to:
            filters.append(ReturnOrder.created_at <= created_to)

        base = (
            select(ReturnOrder)
            .join(AfterSaleOrder, AfterSaleOrder.id == ReturnOrder.after_sale_order_id)
            .join(SalesOrder, SalesOrder.id == ReturnOrder.sales_order_id)
            .join(Customer, Customer.id == AfterSaleOrder.customer_id)
            .join(Warehouse, Warehouse.id == ReturnOrder.warehouse_id)
            .outerjoin(ReturnOrderItem, ReturnOrderItem.return_order_id == ReturnOrder.id)
            .where(*filters)
            .group_by(
                ReturnOrder.id,
                AfterSaleOrder.id,
                SalesOrder.id,
                Customer.id,
                Warehouse.id,
            )
        )
        total = int(self.session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        stmt = (
            select(
                ReturnOrder,
                AfterSaleOrder.after_sale_no,
                SalesOrder.order_no,
                Customer.name,
                Warehouse.name,
                expected,
                received,
                inbound,
            )
            .join(AfterSaleOrder, AfterSaleOrder.id == ReturnOrder.after_sale_order_id)
            .join(SalesOrder, SalesOrder.id == ReturnOrder.sales_order_id)
            .join(Customer, Customer.id == AfterSaleOrder.customer_id)
            .join(Warehouse, Warehouse.id == ReturnOrder.warehouse_id)
            .outerjoin(ReturnOrderItem, ReturnOrderItem.return_order_id == ReturnOrder.id)
            .where(*filters)
            .group_by(
                ReturnOrder.id,
                AfterSaleOrder.id,
                SalesOrder.id,
                Customer.id,
                Warehouse.id,
            )
            .order_by(ReturnOrder.created_at.desc(), ReturnOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total
