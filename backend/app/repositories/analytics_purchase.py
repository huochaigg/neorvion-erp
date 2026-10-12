"""采购报表聚合。采购额、收货量、退货出库都在 SQL 完成。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from app.core.analytics import (
    PURCHASE_INVALID_STATUSES,
    PURCHASE_PARTIALLY_RECEIVED,
    PURCHASE_RETURN_INVALID_STATUSES,
    PURCHASE_RETURN_PENDING_STATUSES,
    PURCHASE_WAITING_RECEIPT,
    int_or_zero,
    money,
)
from app.models.inventory import InventoryTransaction, InventoryTransactionType
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.purchase_receipt import PurchaseReceipt, PurchaseReceiptItem, PurchaseReceiptStatus
from app.models.purchase_return import PURCHASE_RETURN_REFERENCE, PurchaseReturn
from app.models.supplier import Supplier
from app.models.supplier_refund import SupplierRefundRecord, SupplierRefundRecordStatus
from app.repositories.base import BaseRepository

_LINE_AMOUNT = func.coalesce(PurchaseOrderItem.unit_price, 0) * PurchaseOrderItem.quantity


class PurchaseAnalyticsRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def _tenant_orders(self):
        return PurchaseOrder.tenant_id == self.ensure_tenant()

    def _valid_status(self):
        return PurchaseOrder.status.notin_(tuple(PURCHASE_INVALID_STATUSES))

    def _warehouse(self, warehouse_id: int | None, column=None):
        if warehouse_id is None:
            return true()
        target = column if column is not None else PurchaseOrder.warehouse_id
        return target == warehouse_id

    def purchase_amount_and_count(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> tuple[Decimal, int]:
        """
        统计口径：有效采购单（排除 DRAFT / REJECTED / CANCELLED）。
        时间范围：PurchaseOrder.created_at ∈ [start, end_exclusive)。
        返回值：(purchase_amount, purchase_order_count)。
        关键 SQL 思路：COUNT 主表；金额 JOIN items SUM(COALESCE(unit_price,0)*quantity)。
        """
        tenant_id = self.ensure_tenant()
        amount_stmt = (
            select(func.coalesce(func.sum(_LINE_AMOUNT), 0))
            .select_from(PurchaseOrderItem)
            .join(
                PurchaseOrder,
                (PurchaseOrderItem.tenant_id == PurchaseOrder.tenant_id)
                & (PurchaseOrderItem.purchase_order_id == PurchaseOrder.id),
            )
            .where(
                PurchaseOrderItem.tenant_id == tenant_id,
                self._tenant_orders(),
                PurchaseOrder.created_at >= start,
                PurchaseOrder.created_at < end_exclusive,
                self._valid_status(),
                self._warehouse(warehouse_id),
            )
        )
        count_stmt = select(func.count(PurchaseOrder.id)).where(
            self._tenant_orders(),
            PurchaseOrder.created_at >= start,
            PurchaseOrder.created_at < end_exclusive,
            self._valid_status(),
            self._warehouse(warehouse_id),
        )
        return money(self.session.execute(amount_stmt).scalar_one()), int_or_zero(
            self.session.execute(count_stmt).scalar_one()
        )

    def received_quantity(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> int:
        """确认收货才算入库。按 COALESCE(received_at, created_at) 落入区间，仅 CONFIRMED。"""
        tenant_id = self.ensure_tenant()
        received_at = func.coalesce(PurchaseReceipt.received_at, PurchaseReceipt.created_at)
        stmt = (
            select(func.coalesce(func.sum(PurchaseReceiptItem.received_quantity), 0))
            .select_from(PurchaseReceiptItem)
            .join(
                PurchaseReceipt,
                (PurchaseReceiptItem.tenant_id == PurchaseReceipt.tenant_id)
                & (PurchaseReceiptItem.purchase_receipt_id == PurchaseReceipt.id),
            )
            .where(
                PurchaseReceiptItem.tenant_id == tenant_id,
                PurchaseReceipt.tenant_id == tenant_id,
                PurchaseReceipt.status == PurchaseReceiptStatus.CONFIRMED.value,
                received_at >= start,
                received_at < end_exclusive,
                self._warehouse(warehouse_id, PurchaseReceipt.warehouse_id),
            )
        )
        return int_or_zero(self.session.execute(stmt).scalar_one())

    def purchase_return_metrics(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> tuple[int, Decimal]:
        tenant_id = self.ensure_tenant()
        count_stmt = select(func.count(PurchaseReturn.id)).where(
            PurchaseReturn.tenant_id == tenant_id,
            PurchaseReturn.created_at >= start,
            PurchaseReturn.created_at < end_exclusive,
            PurchaseReturn.status.notin_(tuple(PURCHASE_RETURN_INVALID_STATUSES)),
            self._warehouse(warehouse_id, PurchaseReturn.warehouse_id),
        )
        amount_stmt = select(
            func.coalesce(func.sum(PurchaseReturn.requested_refund_amount), 0)
        ).where(
            PurchaseReturn.tenant_id == tenant_id,
            PurchaseReturn.created_at >= start,
            PurchaseReturn.created_at < end_exclusive,
            PurchaseReturn.status.notin_(tuple(PURCHASE_RETURN_INVALID_STATUSES)),
            self._warehouse(warehouse_id, PurchaseReturn.warehouse_id),
        )
        return int_or_zero(self.session.execute(count_stmt).scalar_one()), money(
            self.session.execute(amount_stmt).scalar_one()
        )

    def purchase_return_outbound_quantity(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> int:
        """实际退给供应商的数量：库存流水 PURCHASE_RETURN_OUTBOUND 的 |change_quantity|。"""
        tenant_id = self.ensure_tenant()
        stmt = select(
            func.coalesce(func.sum(func.abs(InventoryTransaction.change_quantity)), 0)
        ).where(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.type == InventoryTransactionType.PURCHASE_RETURN_OUTBOUND.value,
            InventoryTransaction.created_at >= start,
            InventoryTransaction.created_at < end_exclusive,
            self._warehouse(warehouse_id, InventoryTransaction.warehouse_id),
        )
        return int_or_zero(self.session.execute(stmt).scalar_one())

    def supplier_refund_amount(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> Decimal:
        """只统计 SUCCESS。时间取 COALESCE(received_at, created_at)。"""
        tenant_id = self.ensure_tenant()
        refund_at = func.coalesce(SupplierRefundRecord.received_at, SupplierRefundRecord.created_at)
        stmt = (
            select(func.coalesce(func.sum(SupplierRefundRecord.amount), 0))
            .select_from(SupplierRefundRecord)
            .join(
                PurchaseReturn,
                (SupplierRefundRecord.tenant_id == PurchaseReturn.tenant_id)
                & (SupplierRefundRecord.purchase_return_id == PurchaseReturn.id),
            )
            .where(
                SupplierRefundRecord.tenant_id == tenant_id,
                SupplierRefundRecord.status == SupplierRefundRecordStatus.SUCCESS.value,
                refund_at >= start,
                refund_at < end_exclusive,
                self._warehouse(warehouse_id, PurchaseReturn.warehouse_id),
            )
        )
        return money(self.session.execute(stmt).scalar_one())

    def pending_receipt_count(self, warehouse_id: int | None = None) -> int:
        return int_or_zero(
            self.session.execute(
                select(func.count(PurchaseOrder.id)).where(
                    self._tenant_orders(),
                    PurchaseOrder.status.in_(
                        (PURCHASE_WAITING_RECEIPT, PURCHASE_PARTIALLY_RECEIVED)
                    ),
                    self._warehouse(warehouse_id),
                )
            ).scalar_one()
        )

    def pending_purchase_return_count(self, warehouse_id: int | None = None) -> int:
        return int_or_zero(
            self.session.execute(
                select(func.count(PurchaseReturn.id)).where(
                    PurchaseReturn.tenant_id == self.ensure_tenant(),
                    PurchaseReturn.status.in_(tuple(PURCHASE_RETURN_PENDING_STATUSES)),
                    self._warehouse(warehouse_id, PurchaseReturn.warehouse_id),
                )
            ).scalar_one()
        )

    def count_by_status(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> dict[str, int]:
        stmt = (
            select(PurchaseOrder.status, func.count(PurchaseOrder.id))
            .where(
                self._tenant_orders(),
                PurchaseOrder.created_at >= start,
                PurchaseOrder.created_at < end_exclusive,
                self._warehouse(warehouse_id),
            )
            .group_by(PurchaseOrder.status)
        )
        counts = {status.value: 0 for status in PurchaseOrderStatus}
        for status, count in self.session.execute(stmt):
            counts[str(status)] = int_or_zero(count)
        return counts

    def daily_purchase_trend(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        """按 DATE(created_at) 聚合有效采购单数和采购额。"""
        day = func.date(PurchaseOrder.created_at)
        stmt = (
            select(
                day.label("bucket"),
                func.count(func.distinct(PurchaseOrder.id)).label("order_count"),
                func.coalesce(func.sum(_LINE_AMOUNT), 0).label("purchase_amount"),
            )
            .select_from(PurchaseOrder)
            .outerjoin(
                PurchaseOrderItem,
                (PurchaseOrderItem.tenant_id == PurchaseOrder.tenant_id)
                & (PurchaseOrderItem.purchase_order_id == PurchaseOrder.id),
            )
            .where(
                self._tenant_orders(),
                PurchaseOrder.created_at >= start,
                PurchaseOrder.created_at < end_exclusive,
                self._valid_status(),
                self._warehouse(warehouse_id),
            )
            .group_by(day)
            .order_by(day)
        )
        return list(self.session.execute(stmt).all())

    def daily_received_trend(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        tenant_id = self.ensure_tenant()
        received_at = func.coalesce(PurchaseReceipt.received_at, PurchaseReceipt.created_at)
        day = func.date(received_at)
        stmt = (
            select(
                day.label("bucket"),
                func.coalesce(func.sum(PurchaseReceiptItem.received_quantity), 0),
            )
            .select_from(PurchaseReceiptItem)
            .join(
                PurchaseReceipt,
                (PurchaseReceiptItem.tenant_id == PurchaseReceipt.tenant_id)
                & (PurchaseReceiptItem.purchase_receipt_id == PurchaseReceipt.id),
            )
            .where(
                PurchaseReceiptItem.tenant_id == tenant_id,
                PurchaseReceipt.status == PurchaseReceiptStatus.CONFIRMED.value,
                received_at >= start,
                received_at < end_exclusive,
                self._warehouse(warehouse_id, PurchaseReceipt.warehouse_id),
            )
            .group_by(day)
            .order_by(day)
        )
        return list(self.session.execute(stmt).all())

    def daily_purchase_return_outbound_trend(
        self,
        start: datetime,
        end_exclusive: datetime,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        tenant_id = self.ensure_tenant()
        day = func.date(InventoryTransaction.created_at)
        stmt = (
            select(
                day.label("bucket"),
                func.coalesce(func.sum(func.abs(InventoryTransaction.change_quantity)), 0),
            )
            .where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.type
                == InventoryTransactionType.PURCHASE_RETURN_OUTBOUND.value,
                InventoryTransaction.created_at >= start,
                InventoryTransaction.created_at < end_exclusive,
                self._warehouse(warehouse_id, InventoryTransaction.warehouse_id),
            )
            .group_by(day)
            .order_by(day)
        )
        return list(self.session.execute(stmt).all())

    def top_suppliers(
        self,
        start: datetime,
        end_exclusive: datetime,
        limit: int,
        warehouse_id: int | None = None,
    ) -> list[tuple]:
        """一次 JOIN suppliers 返回名称，按采购额排序。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                Supplier.id,
                Supplier.name,
                func.count(func.distinct(PurchaseOrder.id)).label("order_count"),
                func.coalesce(func.sum(_LINE_AMOUNT), 0).label("purchase_amount"),
            )
            .select_from(PurchaseOrder)
            .join(
                Supplier,
                (PurchaseOrder.tenant_id == Supplier.tenant_id)
                & (PurchaseOrder.supplier_id == Supplier.id),
            )
            .outerjoin(
                PurchaseOrderItem,
                (PurchaseOrderItem.tenant_id == PurchaseOrder.tenant_id)
                & (PurchaseOrderItem.purchase_order_id == PurchaseOrder.id),
            )
            .where(
                self._tenant_orders(),
                PurchaseOrder.created_at >= start,
                PurchaseOrder.created_at < end_exclusive,
                self._valid_status(),
                self._warehouse(warehouse_id),
                Supplier.tenant_id == tenant_id,
            )
            .group_by(Supplier.id, Supplier.name)
            .order_by(func.coalesce(func.sum(_LINE_AMOUNT), 0).desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).all())

    def received_quantity_by_supplier(
        self,
        start: datetime,
        end_exclusive: datetime,
        supplier_ids: list[int],
        warehouse_id: int | None = None,
    ) -> dict[int, int]:
        if not supplier_ids:
            return {}
        tenant_id = self.ensure_tenant()
        received_at = func.coalesce(PurchaseReceipt.received_at, PurchaseReceipt.created_at)
        stmt = (
            select(
                PurchaseOrder.supplier_id,
                func.coalesce(func.sum(PurchaseReceiptItem.received_quantity), 0),
            )
            .select_from(PurchaseReceiptItem)
            .join(
                PurchaseReceipt,
                (PurchaseReceiptItem.tenant_id == PurchaseReceipt.tenant_id)
                & (PurchaseReceiptItem.purchase_receipt_id == PurchaseReceipt.id),
            )
            .join(
                PurchaseOrder,
                (PurchaseReceipt.tenant_id == PurchaseOrder.tenant_id)
                & (PurchaseReceipt.purchase_order_id == PurchaseOrder.id),
            )
            .where(
                PurchaseReceiptItem.tenant_id == tenant_id,
                PurchaseReceipt.status == PurchaseReceiptStatus.CONFIRMED.value,
                received_at >= start,
                received_at < end_exclusive,
                PurchaseOrder.supplier_id.in_(supplier_ids),
                self._warehouse(warehouse_id, PurchaseReceipt.warehouse_id),
            )
            .group_by(PurchaseOrder.supplier_id)
        )
        return {int(sid): int_or_zero(qty) for sid, qty in self.session.execute(stmt)}

    def purchase_return_quantity_by_supplier(
        self,
        start: datetime,
        end_exclusive: datetime,
        supplier_ids: list[int],
        warehouse_id: int | None = None,
    ) -> dict[int, int]:
        if not supplier_ids:
            return {}
        tenant_id = self.ensure_tenant()
        stmt = (
            select(
                PurchaseReturn.supplier_id,
                func.coalesce(func.sum(func.abs(InventoryTransaction.change_quantity)), 0),
            )
            .select_from(InventoryTransaction)
            .join(
                PurchaseReturn,
                (InventoryTransaction.tenant_id == PurchaseReturn.tenant_id)
                & (InventoryTransaction.reference_id == PurchaseReturn.id)
                & (InventoryTransaction.reference_type == PURCHASE_RETURN_REFERENCE),
            )
            .where(
                InventoryTransaction.tenant_id == tenant_id,
                InventoryTransaction.type
                == InventoryTransactionType.PURCHASE_RETURN_OUTBOUND.value,
                InventoryTransaction.created_at >= start,
                InventoryTransaction.created_at < end_exclusive,
                PurchaseReturn.supplier_id.in_(supplier_ids),
                self._warehouse(warehouse_id, InventoryTransaction.warehouse_id),
            )
            .group_by(PurchaseReturn.supplier_id)
        )
        return {int(sid): int_or_zero(qty) for sid, qty in self.session.execute(stmt)}
