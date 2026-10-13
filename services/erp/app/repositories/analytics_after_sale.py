"""售后报表聚合。售后率分子用 DISTINCT sales_order_id，避免一单多售后重复。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session

from app.core.analytics import AFTER_SALE_INVALID_STATUSES, int_or_zero, money
from app.models.after_sale import AfterSaleItem, AfterSaleOrder, AfterSaleStatus, AfterSaleType
from app.models.refund import RefundRecord, RefundRecordStatus
from app.models.sales_order import SalesOrder
from app.repositories.base import BaseRepository

_RETURN_QTY = func.coalesce(AfterSaleItem.approved_return_quantity, AfterSaleItem.return_quantity)


class AfterSaleAnalyticsRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def _tenant(self):
        return AfterSaleOrder.tenant_id == self.ensure_tenant()

    def _valid(self):
        return AfterSaleOrder.status.notin_(tuple(AFTER_SALE_INVALID_STATUSES))

    def _warehouse_join_filter(self, warehouse_id: int | None):
        if warehouse_id is None:
            return true()
        return SalesOrder.warehouse_id == warehouse_id

    def summary_counts(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> dict[str, int]:
        """
        统计口径：有效售后排除 REJECTED / CANCELLED。
        时间范围：AfterSaleOrder.created_at。
        售后率分子：COUNT(DISTINCT sales_order_id)，不是售后单数量。
        """
        tenant_id = self.ensure_tenant()
        typed = select(
            func.count(AfterSaleOrder.id),
            func.count(func.distinct(AfterSaleOrder.sales_order_id)),
            func.coalesce(
                func.sum(
                    case((AfterSaleOrder.type == AfterSaleType.REFUND_ONLY.value, 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((AfterSaleOrder.type == AfterSaleType.RETURN_ONLY.value, 1), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((AfterSaleOrder.type == AfterSaleType.RETURN_AND_REFUND.value, 1), else_=0)
                ),
                0,
            ),
        ).select_from(AfterSaleOrder)
        if warehouse_id is not None:
            typed = typed.join(
                SalesOrder,
                (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                & (AfterSaleOrder.sales_order_id == SalesOrder.id),
            )
        typed = typed.where(
            AfterSaleOrder.tenant_id == tenant_id,
            AfterSaleOrder.created_at >= start,
            AfterSaleOrder.created_at < end_exclusive,
            self._valid(),
            self._warehouse_join_filter(warehouse_id),
        )
        total, distinct_orders, refund_only, return_only, both = self.session.execute(typed).one()

        qty_stmt = (
            select(func.coalesce(func.sum(_RETURN_QTY), 0))
            .select_from(AfterSaleItem)
            .join(
                AfterSaleOrder,
                (AfterSaleItem.tenant_id == AfterSaleOrder.tenant_id)
                & (AfterSaleItem.after_sale_order_id == AfterSaleOrder.id),
            )
        )
        if warehouse_id is not None:
            qty_stmt = qty_stmt.join(
                SalesOrder,
                (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                & (AfterSaleOrder.sales_order_id == SalesOrder.id),
            )
        qty_stmt = qty_stmt.where(
            AfterSaleItem.tenant_id == tenant_id,
            AfterSaleOrder.created_at >= start,
            AfterSaleOrder.created_at < end_exclusive,
            self._valid(),
            self._warehouse_join_filter(warehouse_id),
        )
        return {
            "after_sale_count": int_or_zero(total),
            "after_sale_sales_order_count": int_or_zero(distinct_orders),
            "refund_only_count": int_or_zero(refund_only),
            "return_only_count": int_or_zero(return_only),
            "return_and_refund_count": int_or_zero(both),
            "return_quantity": int_or_zero(self.session.execute(qty_stmt).scalar_one()),
        }

    def type_counts(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple[str, int]]:
        counts = {item.value: 0 for item in AfterSaleType}
        stmt = select(AfterSaleOrder.type, func.count(AfterSaleOrder.id)).select_from(
            AfterSaleOrder
        )
        if warehouse_id is not None:
            stmt = stmt.join(
                SalesOrder,
                (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                & (AfterSaleOrder.sales_order_id == SalesOrder.id),
            )
        stmt = stmt.where(
            self._tenant(),
            AfterSaleOrder.created_at >= start,
            AfterSaleOrder.created_at < end_exclusive,
            self._valid(),
            self._warehouse_join_filter(warehouse_id),
        ).group_by(AfterSaleOrder.type)
        for type_code, count in self.session.execute(stmt):
            counts[str(type_code)] = int_or_zero(count)
        return [(item.value, counts[item.value]) for item in AfterSaleType]

    def daily_trend(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        tenant_id = self.ensure_tenant()
        day = func.date(AfterSaleOrder.created_at)
        stmt = (
            select(
                day.label("bucket"),
                func.count(func.distinct(AfterSaleOrder.id)).label("after_sale_count"),
                func.coalesce(func.sum(_RETURN_QTY), 0).label("return_quantity"),
            )
            .select_from(AfterSaleOrder)
            .outerjoin(
                AfterSaleItem,
                (AfterSaleItem.tenant_id == AfterSaleOrder.tenant_id)
                & (AfterSaleItem.after_sale_order_id == AfterSaleOrder.id),
            )
        )
        if warehouse_id is not None:
            stmt = stmt.join(
                SalesOrder,
                (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                & (AfterSaleOrder.sales_order_id == SalesOrder.id),
            )
        stmt = (
            stmt.where(
                AfterSaleOrder.tenant_id == tenant_id,
                AfterSaleOrder.created_at >= start,
                AfterSaleOrder.created_at < end_exclusive,
                self._valid(),
                self._warehouse_join_filter(warehouse_id),
            )
            .group_by(day)
            .order_by(day)
        )
        return list(self.session.execute(stmt).all())

    def pending_counts(self, warehouse_id: int | None = None) -> tuple[int, int]:
        tenant_id = self.ensure_tenant()

        def _count(status: str) -> int:
            stmt = select(func.count(AfterSaleOrder.id)).select_from(AfterSaleOrder)
            if warehouse_id is not None:
                stmt = stmt.join(
                    SalesOrder,
                    (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                    & (AfterSaleOrder.sales_order_id == SalesOrder.id),
                )
            stmt = stmt.where(
                AfterSaleOrder.tenant_id == tenant_id,
                AfterSaleOrder.status == status,
                self._warehouse_join_filter(warehouse_id),
            )
            return int_or_zero(self.session.execute(stmt).scalar_one())

        return _count(AfterSaleStatus.PENDING_APPROVAL.value), _count(
            AfterSaleStatus.WAITING_REFUND.value
        )

    def success_refund_amount(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> Decimal:
        tenant_id = self.ensure_tenant()
        refund_at = func.coalesce(RefundRecord.refunded_at, RefundRecord.created_at)
        stmt = select(func.coalesce(func.sum(RefundRecord.amount), 0)).select_from(RefundRecord)
        if warehouse_id is not None:
            stmt = stmt.join(
                AfterSaleOrder,
                (RefundRecord.tenant_id == AfterSaleOrder.tenant_id)
                & (RefundRecord.after_sale_order_id == AfterSaleOrder.id),
            ).join(
                SalesOrder,
                (AfterSaleOrder.tenant_id == SalesOrder.tenant_id)
                & (AfterSaleOrder.sales_order_id == SalesOrder.id),
            )
        stmt = stmt.where(
            RefundRecord.tenant_id == tenant_id,
            RefundRecord.status == RefundRecordStatus.SUCCESS.value,
            refund_at >= start,
            refund_at < end_exclusive,
            self._warehouse_join_filter(warehouse_id),
        )
        return money(self.session.execute(stmt).scalar_one())
