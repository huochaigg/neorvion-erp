from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, selectinload

from app.models.customer import Customer
from app.models.product import Product, ProductSku
from app.models.sales_order import SalesOrder, SalesOrderItem
from app.models.user import User
from app.models.warehouse import Warehouse
from app.repositories.base import BaseRepository


class SalesOrderRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_in_tenant(self, order_id: int) -> SalesOrder | None:
        """详情一次 selectinload 客户、仓库、明细和 SKU，避免循环查名称。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(SalesOrder)
            .options(
                selectinload(SalesOrder.customer),
                selectinload(SalesOrder.warehouse),
                selectinload(SalesOrder.items)
                .selectinload(SalesOrderItem.sku)
                .selectinload(ProductSku.product),
            )
            .where(SalesOrder.tenant_id == tenant_id, SalesOrder.id == order_id)
        )
        return self.session.scalars(stmt).first()

    def get_for_update(self, order_id: int) -> SalesOrder | None:
        """锁订单主行。确认和取消必须先拿到这把锁，才能串行化同一张订单。

        只锁本租户的这一行。别的租户即使猜到 id，WHERE tenant_id 也对不上。
        """
        tenant_id = self.ensure_tenant()
        stmt = (
            select(SalesOrder)
            .where(SalesOrder.tenant_id == tenant_id, SalesOrder.id == order_id)
            .with_for_update()
        )
        return self.session.scalars(stmt).first()

    def list_items(self, order_id: int) -> list[SalesOrderItem]:
        """按 sku_id 升序取出明细。确认/取消按这个顺序动库存，降低死锁概率。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(SalesOrderItem)
            .options(selectinload(SalesOrderItem.sku).selectinload(ProductSku.product))
            .where(
                SalesOrderItem.tenant_id == tenant_id,
                SalesOrderItem.sales_order_id == order_id,
            )
            .order_by(SalesOrderItem.sku_id.asc(), SalesOrderItem.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_page(
        self,
        *,
        q: str | None,
        order_no: str | None,
        external_order_no: str | None,
        customer_id: int | None,
        warehouse_id: int | None,
        sku_code: str | None,
        product_name: str | None,
        status: str | None,
        source: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple], int]:
        """列表 JOIN 客户/仓库/创建人，SQL 聚合 SKU 种类、数量和金额，避免 N+1。"""
        tenant_id = self.ensure_tenant()
        filters = [SalesOrder.tenant_id == tenant_id]
        if order_no:
            filters.append(SalesOrder.order_no.like(f"%{order_no}%"))
        if external_order_no:
            filters.append(SalesOrder.external_order_no.like(f"%{external_order_no}%"))
        if customer_id:
            filters.append(SalesOrder.customer_id == customer_id)
        if warehouse_id:
            filters.append(SalesOrder.warehouse_id == warehouse_id)
        if status:
            filters.append(SalesOrder.status == status)
        if source:
            filters.append(SalesOrder.source == source)
        if created_from is not None:
            filters.append(SalesOrder.created_at >= created_from)
        if created_to is not None:
            filters.append(SalesOrder.created_at <= created_to)
        if q:
            pattern = f"%{q}%"
            filters.append(
                or_(
                    SalesOrder.order_no.like(pattern),
                    SalesOrder.external_order_no.like(pattern),
                    Customer.name.like(pattern),
                    Customer.code.like(pattern),
                )
            )
        if sku_code or product_name:
            exists_filters = [
                SalesOrderItem.tenant_id == tenant_id,
                SalesOrderItem.sales_order_id == SalesOrder.id,
                ProductSku.tenant_id == tenant_id,
                Product.tenant_id == tenant_id,
            ]
            if sku_code:
                exists_filters.append(ProductSku.sku_code.like(f"%{sku_code}%"))
            if product_name:
                exists_filters.append(Product.name.like(f"%{product_name}%"))
            exists_stmt = (
                select(SalesOrderItem.id)
                .join(
                    ProductSku,
                    and_(
                        ProductSku.tenant_id == SalesOrderItem.tenant_id,
                        ProductSku.id == SalesOrderItem.sku_id,
                    ),
                )
                .join(
                    Product,
                    and_(
                        Product.tenant_id == ProductSku.tenant_id,
                        Product.id == ProductSku.product_id,
                    ),
                )
                .where(*exists_filters)
            )
            filters.append(exists_stmt.exists())

        count_stmt = (
            select(func.count(SalesOrder.id))
            .select_from(SalesOrder)
            .join(
                Customer,
                and_(
                    Customer.tenant_id == SalesOrder.tenant_id,
                    Customer.id == SalesOrder.customer_id,
                ),
            )
            .where(*filters)
        )
        total = int(self.session.scalar(count_stmt) or 0)
        sku_count = func.count(func.distinct(SalesOrderItem.sku_id))
        total_qty = func.coalesce(func.sum(SalesOrderItem.quantity), 0)
        priced = SalesOrderItem.quantity * SalesOrderItem.unit_price
        total_amount = func.sum(priced)
        stmt = (
            select(
                SalesOrder,
                Customer.name,
                Warehouse.name,
                User.display_name,
                sku_count,
                total_qty,
                total_amount,
            )
            .join(
                Customer,
                and_(
                    Customer.tenant_id == SalesOrder.tenant_id,
                    Customer.id == SalesOrder.customer_id,
                ),
            )
            .join(
                Warehouse,
                and_(
                    Warehouse.tenant_id == SalesOrder.tenant_id,
                    Warehouse.id == SalesOrder.warehouse_id,
                ),
            )
            .outerjoin(User, User.id == SalesOrder.created_by)
            .outerjoin(
                SalesOrderItem,
                and_(
                    SalesOrderItem.tenant_id == SalesOrder.tenant_id,
                    SalesOrderItem.sales_order_id == SalesOrder.id,
                ),
            )
            .where(*filters)
            .group_by(SalesOrder.id, Customer.name, Warehouse.name, User.display_name)
            .order_by(SalesOrder.created_at.desc(), SalesOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.execute(stmt).all()), total

    def count_by_customer(self, customer_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(SalesOrder.id)).where(
            SalesOrder.tenant_id == tenant_id,
            SalesOrder.customer_id == customer_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def add(self, order: SalesOrder) -> SalesOrder:
        self.session.add(order)
        return order

    def add_item(self, item: SalesOrderItem) -> SalesOrderItem:
        self.session.add(item)
        return item

    def delete_items(self, order_id: int) -> None:
        tenant_id = self.ensure_tenant()
        stmt = delete(SalesOrderItem).where(
            SalesOrderItem.tenant_id == tenant_id,
            SalesOrderItem.sales_order_id == order_id,
        )
        self.session.execute(stmt)

    def count_reserve_transactions(self, order_id: int, tx_type: str) -> int:
        """确认失败后检查有没有残留有效流水。流水和订单在同一事务，rollback 后应为 0。"""
        from app.models.inventory import InventoryTransaction

        tenant_id = self.ensure_tenant()
        stmt = select(func.count(InventoryTransaction.id)).where(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.reference_type == "SALES_ORDER",
            InventoryTransaction.reference_id == order_id,
            InventoryTransaction.type == tx_type,
        )
        return int(self.session.scalar(stmt) or 0)

    def transition_if_status(
        self,
        *,
        order_id: int,
        expected_status: str,
        values: dict[str, Any],
    ) -> int:
        """备用的条件 UPDATE。确认/取消主路径用 FOR UPDATE，这里留给需要 rowcount 的检查。"""
        from sqlalchemy import update

        tenant_id = self.ensure_tenant()
        stmt = (
            update(SalesOrder)
            .where(
                SalesOrder.tenant_id == tenant_id,
                SalesOrder.id == order_id,
                SalesOrder.status == expected_status,
            )
            .values(**values)
        )
        result: CursorResult[Any] = self.session.execute(stmt)  # type: ignore[assignment]
        self.session.expire_all()
        return int(result.rowcount or 0)
