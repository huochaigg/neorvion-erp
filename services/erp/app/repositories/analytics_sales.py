"""销售报表聚合。金额与计数都在 MySQL 完成，不把明细拉进 Python。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session

from app.core.analytics import (
    SALES_CANCELLED,
    SALES_COMPLETED,
    SALES_INVALID_STATUSES,
    SALES_PENDING_CONFIRMATION,
    SALES_WAITING_OUTBOUND,
    int_or_zero,
    money,
)
from app.models.customer import Customer
from app.models.product import Product, ProductSku
from app.models.refund import RefundRecord, RefundRecordStatus
from app.models.sales_order import SalesOrder, SalesOrderItem, SalesOrderStatus
from app.repositories.base import BaseRepository

_LINE_AMOUNT = func.coalesce(SalesOrderItem.unit_price, 0) * SalesOrderItem.quantity


class SalesAnalyticsRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def _tenant_orders(self):
        tenant_id = self.ensure_tenant()
        return SalesOrder.tenant_id == tenant_id

    def _in_range(self, column, start: datetime, end_exclusive: datetime):
        return column >= start, column < end_exclusive

    def _valid_status(self):
        return SalesOrder.status.notin_(tuple(SALES_INVALID_STATUSES))

    def _warehouse(self, warehouse_id: int | None):
        if warehouse_id is None:
            return true()
        return SalesOrder.warehouse_id == warehouse_id

    def count_by_status(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> dict[str, int]:
        """按当前真实销售状态枚举计数，不要硬编码旧状态。"""
        created_ge, created_lt = self._in_range(SalesOrder.created_at, start, end_exclusive)
        stmt = (
            select(SalesOrder.status, func.count(SalesOrder.id))
            .where(
                self._tenant_orders(),
                created_ge,
                created_lt,
                self._warehouse(warehouse_id),
            )
            .group_by(SalesOrder.status)
        )
        counts = {status.value: 0 for status in SalesOrderStatus}
        for status, count in self.session.execute(stmt):
            counts[str(status)] = int_or_zero(count)
        return counts

    def sales_amount_and_order_count(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> tuple[Decimal, int]:
        """
        统计口径：有效销售订单（排除 DRAFT / CANCELLED）。
        时间范围：SalesOrder.created_at ∈ [start, end_exclusive)。
        过滤状态：status NOT IN ('DRAFT','CANCELLED')。
        返回值：(gross_sales_amount, valid_order_count)。
        关键 SQL 思路：订单计数 COUNT(DISTINCT sales_orders.id)；
        金额 JOIN items 后 SUM(COALESCE(unit_price,0)*quantity)。
        """
        created_ge, created_lt = self._in_range(SalesOrder.created_at, start, end_exclusive)
        amount_stmt = (
            select(func.coalesce(func.sum(_LINE_AMOUNT), 0))
            .select_from(SalesOrderItem)
            .join(
                SalesOrder,
                (SalesOrderItem.tenant_id == SalesOrder.tenant_id)
                & (SalesOrderItem.sales_order_id == SalesOrder.id),
            )
            .where(
                self._tenant_orders(),
                SalesOrderItem.tenant_id == self.ensure_tenant(),
                created_ge,
                created_lt,
                self._valid_status(),
                self._warehouse(warehouse_id),
            )
        )
        count_stmt = select(func.count(SalesOrder.id)).where(
            self._tenant_orders(),
            created_ge,
            created_lt,
            self._valid_status(),
            self._warehouse(warehouse_id),
        )
        amount = money(self.session.execute(amount_stmt).scalar_one())
        count = int_or_zero(self.session.execute(count_stmt).scalar_one())
        return amount, count

    def success_refund_amount(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> Decimal:
        """
        只统计 SUCCESS 退款。PENDING / FAILED 不扣净销售额。
        时间取 COALESCE(refunded_at, created_at)，与确认成功时刻对齐。
        可选 warehouse_id 通过售后关联的销售订单仓库过滤。
        """
        from app.models.after_sale import AfterSaleOrder

        tenant_id = self.ensure_tenant()
        refund_at = func.coalesce(RefundRecord.refunded_at, RefundRecord.created_at)
        stmt = (
            select(func.coalesce(func.sum(RefundRecord.amount), 0))
            .select_from(RefundRecord)
            .join(
                AfterSaleOrder,
                (RefundRecord.tenant_id == AfterSaleOrder.tenant_id)
                & (RefundRecord.after_sale_order_id == AfterSaleOrder.id),
            )
            .join(
                SalesOrder,
                (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                & (AfterSaleOrder.sales_order_id == SalesOrder.id),
            )
            .where(
                RefundRecord.tenant_id == tenant_id,
                AfterSaleOrder.tenant_id == tenant_id,
                SalesOrder.tenant_id == tenant_id,
                RefundRecord.status == RefundRecordStatus.SUCCESS.value,
                refund_at >= start,
                refund_at < end_exclusive,
                self._warehouse(warehouse_id),
            )
        )
        return money(self.session.execute(stmt).scalar_one())

    def daily_sales_trend(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        """
        按日 GROUP BY DATE(created_at)。
        关键 SQL 思路：订单日桶用 DATE(sales_orders.created_at)；
        金额仍 JOIN items；取消/草稿不进结果。缺失日由 Service 补 0。
        """
        created_ge, created_lt = self._in_range(SalesOrder.created_at, start, end_exclusive)
        day = func.date(SalesOrder.created_at)
        stmt = (
            select(
                day.label("bucket"),
                func.count(func.distinct(SalesOrder.id)).label("order_count"),
                func.coalesce(func.sum(_LINE_AMOUNT), 0).label("sales_amount"),
            )
            .select_from(SalesOrder)
            .outerjoin(
                SalesOrderItem,
                (SalesOrderItem.tenant_id == SalesOrder.tenant_id)
                & (SalesOrderItem.sales_order_id == SalesOrder.id),
            )
            .where(
                self._tenant_orders(),
                created_ge,
                created_lt,
                self._valid_status(),
                self._warehouse(warehouse_id),
            )
            .group_by(day)
            .order_by(day)
        )
        return list(self.session.execute(stmt).all())

    def daily_refund_trend(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        from app.models.after_sale import AfterSaleOrder

        tenant_id = self.ensure_tenant()
        refund_at = func.coalesce(RefundRecord.refunded_at, RefundRecord.created_at)
        day = func.date(refund_at)
        stmt = (
            select(
                day.label("bucket"),
                func.coalesce(func.sum(RefundRecord.amount), 0).label("refund_amount"),
            )
            .select_from(RefundRecord)
            .join(
                AfterSaleOrder,
                (RefundRecord.tenant_id == AfterSaleOrder.tenant_id)
                & (RefundRecord.after_sale_order_id == AfterSaleOrder.id),
            )
            .join(
                SalesOrder,
                (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                & (AfterSaleOrder.sales_order_id == SalesOrder.id),
            )
            .where(
                RefundRecord.tenant_id == tenant_id,
                RefundRecord.status == RefundRecordStatus.SUCCESS.value,
                refund_at >= start,
                refund_at < end_exclusive,
                self._warehouse(warehouse_id),
            )
            .group_by(day)
            .order_by(day)
        )
        return list(self.session.execute(stmt).all())

    def top_skus(
        self,
        start: datetime,
        end_exclusive: datetime,
        limit: int,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        """
        Top SKU：有效订单明细按 sku_id 聚合，一次 JOIN 带回编码和商品名，避免 N+1。
        排序：销量 desc，销售额 desc。
        """
        created_ge, created_lt = self._in_range(SalesOrder.created_at, start, end_exclusive)
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                ProductSku.id,
                ProductSku.sku_code,
                ProductSku.name,
                Product.id,
                Product.name,
                ProductSku.spec_values,
                func.coalesce(func.sum(SalesOrderItem.quantity), 0).label("sales_quantity"),
                func.coalesce(func.sum(_LINE_AMOUNT), 0).label("sales_amount"),
                func.count(func.distinct(SalesOrder.id)).label("order_count"),
            )
            .select_from(SalesOrderItem)
            .join(
                SalesOrder,
                (SalesOrderItem.tenant_id == SalesOrder.tenant_id)
                & (SalesOrderItem.sales_order_id == SalesOrder.id),
            )
            .join(
                ProductSku,
                (SalesOrderItem.tenant_id == ProductSku.tenant_id)
                & (SalesOrderItem.sku_id == ProductSku.id),
            )
            .join(
                Product,
                (ProductSku.tenant_id == Product.tenant_id) & (ProductSku.product_id == Product.id),
            )
            .where(
                SalesOrderItem.tenant_id == tenant_id,
                self._tenant_orders(),
                created_ge,
                created_lt,
                self._valid_status(),
                self._warehouse(warehouse_id),
            )
            .group_by(
                ProductSku.id,
                ProductSku.sku_code,
                ProductSku.name,
                Product.id,
                Product.name,
                ProductSku.spec_values,
            )
            .order_by(
                func.coalesce(func.sum(SalesOrderItem.quantity), 0).desc(),
                func.coalesce(func.sum(_LINE_AMOUNT), 0).desc(),
            )
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

    def sku_sales(
        self,
        sku_code: str,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> tuple | None:
        """按 SKU 精确聚合有效订单销量，避免用 Top-N 结果冒充目标 SKU 统计。"""
        created_ge, created_lt = self._in_range(SalesOrder.created_at, start, end_exclusive)
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                ProductSku.id,
                ProductSku.sku_code,
                ProductSku.name,
                func.coalesce(
                    func.sum(case((SalesOrder.id.is_not(None), SalesOrderItem.quantity), else_=0)),
                    0,
                ).label("sales_quantity"),
                func.count(func.distinct(SalesOrder.id)).label("order_count"),
            )
            .select_from(ProductSku)
            .outerjoin(
                SalesOrderItem,
                (SalesOrderItem.tenant_id == ProductSku.tenant_id)
                & (SalesOrderItem.sku_id == ProductSku.id),
            )
            .outerjoin(
                SalesOrder,
                (SalesOrderItem.tenant_id == SalesOrder.tenant_id)
                & (SalesOrderItem.sales_order_id == SalesOrder.id)
                & created_ge
                & created_lt
                & self._valid_status()
                & self._warehouse(warehouse_id),
            )
            .where(ProductSku.tenant_id == tenant_id, ProductSku.sku_code == sku_code)
            .group_by(ProductSku.id, ProductSku.sku_code, ProductSku.name)
        )
        return self.session.execute(stmt).one_or_none()

    def top_products(
        self,
        start: datetime,
        end_exclusive: datetime,
        limit: int,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        created_ge, created_lt = self._in_range(SalesOrder.created_at, start, end_exclusive)
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                Product.id,
                Product.name,
                func.coalesce(func.sum(SalesOrderItem.quantity), 0).label("sales_quantity"),
                func.coalesce(func.sum(_LINE_AMOUNT), 0).label("sales_amount"),
                func.count(func.distinct(ProductSku.id)).label("sku_count"),
            )
            .select_from(SalesOrderItem)
            .join(
                SalesOrder,
                (SalesOrderItem.tenant_id == SalesOrder.tenant_id)
                & (SalesOrderItem.sales_order_id == SalesOrder.id),
            )
            .join(
                ProductSku,
                (SalesOrderItem.tenant_id == ProductSku.tenant_id)
                & (SalesOrderItem.sku_id == ProductSku.id),
            )
            .join(
                Product,
                (ProductSku.tenant_id == Product.tenant_id) & (ProductSku.product_id == Product.id),
            )
            .where(
                SalesOrderItem.tenant_id == tenant_id,
                self._tenant_orders(),
                created_ge,
                created_lt,
                self._valid_status(),
                self._warehouse(warehouse_id),
            )
            .group_by(Product.id, Product.name)
            .order_by(
                func.coalesce(func.sum(_LINE_AMOUNT), 0).desc(),
                func.coalesce(func.sum(SalesOrderItem.quantity), 0).desc(),
            )
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

    def top_customers(
        self,
        start: datetime,
        end_exclusive: datetime,
        limit: int,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        """
        Top Customer：按客户聚合有效订单金额。客户名一次 JOIN customers，不循环查。
        退款金额由 Service 再按 customer_id 合并 SUCCESS 退款。
        """
        created_ge, created_lt = self._in_range(SalesOrder.created_at, start, end_exclusive)
        stmt = (
            select(
                Customer.id,
                Customer.name,
                func.count(func.distinct(SalesOrder.id)).label("order_count"),
                func.coalesce(func.sum(_LINE_AMOUNT), 0).label("sales_amount"),
            )
            .select_from(SalesOrder)
            .join(
                Customer,
                (SalesOrder.tenant_id == Customer.tenant_id)
                & (SalesOrder.customer_id == Customer.id),
            )
            .outerjoin(
                SalesOrderItem,
                (SalesOrderItem.tenant_id == SalesOrder.tenant_id)
                & (SalesOrderItem.sales_order_id == SalesOrder.id),
            )
            .where(
                self._tenant_orders(),
                created_ge,
                created_lt,
                self._valid_status(),
                self._warehouse(warehouse_id),
            )
            .group_by(Customer.id, Customer.name)
            .order_by(func.coalesce(func.sum(_LINE_AMOUNT), 0).desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

    def success_refund_amount_by_customer(
        self,
        start: datetime,
        end_exclusive: datetime,
        customer_ids: list[int],
        warehouse_id: int | None = None,
    ) -> dict[int, Decimal]:
        if not customer_ids:
            return {}
        from app.models.after_sale import AfterSaleOrder

        tenant_id = self.ensure_tenant()
        refund_at = func.coalesce(RefundRecord.refunded_at, RefundRecord.created_at)
        stmt = (
            select(
                AfterSaleOrder.customer_id,
                func.coalesce(func.sum(RefundRecord.amount), 0),
            )
            .select_from(RefundRecord)
            .join(
                AfterSaleOrder,
                (RefundRecord.tenant_id == AfterSaleOrder.tenant_id)
                & (RefundRecord.after_sale_order_id == AfterSaleOrder.id),
            )
            .join(
                SalesOrder,
                (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                & (AfterSaleOrder.sales_order_id == SalesOrder.id),
            )
            .where(
                RefundRecord.tenant_id == tenant_id,
                RefundRecord.status == RefundRecordStatus.SUCCESS.value,
                refund_at >= start,
                refund_at < end_exclusive,
                AfterSaleOrder.customer_id.in_(customer_ids),
                self._warehouse(warehouse_id),
            )
            .group_by(AfterSaleOrder.customer_id)
        )
        return {int(cid): money(amount) for cid, amount in self.session.execute(stmt)}

    def pending_counts(self, warehouse_id: int | None = None) -> tuple[int, int]:
        """待确认 / 待出库是当前快照，不受报表时间范围影响。"""
        pending = int_or_zero(
            self.session.execute(
                select(func.count(SalesOrder.id)).where(
                    self._tenant_orders(),
                    SalesOrder.status == SALES_PENDING_CONFIRMATION,
                    self._warehouse(warehouse_id),
                )
            ).scalar_one()
        )
        waiting = int_or_zero(
            self.session.execute(
                select(func.count(SalesOrder.id)).where(
                    self._tenant_orders(),
                    SalesOrder.status == SALES_WAITING_OUTBOUND,
                    self._warehouse(warehouse_id),
                )
            ).scalar_one()
        )
        return pending, waiting

    def completed_and_cancelled_counts(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> tuple[int, int, int]:
        created_ge, created_lt = self._in_range(SalesOrder.created_at, start, end_exclusive)
        stmt = select(
            func.coalesce(
                func.sum(case((SalesOrder.status == SALES_COMPLETED, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((SalesOrder.status == SALES_CANCELLED, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((SalesOrder.status == SalesOrderStatus.DRAFT.value, 1), else_=0)),
                0,
            ),
        ).where(
            self._tenant_orders(),
            created_ge,
            created_lt,
            self._warehouse(warehouse_id),
        )
        completed, cancelled, draft = self.session.execute(stmt).one()
        return int_or_zero(completed), int_or_zero(cancelled), int_or_zero(draft)
