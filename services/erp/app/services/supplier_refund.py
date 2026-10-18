"""供应商退款记录。确认退款不修改 Inventory；库存已在退货出库时减少。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import AggregateType, EventType
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.purchase_return import (
    PurchaseReturnRefundStatus,
    PurchaseReturnSettlementType,
    PurchaseReturnStatus,
)
from app.models.supplier_refund import SupplierRefundRecord, SupplierRefundRecordStatus
from app.models.user import User
from app.repositories.purchase_return import PurchaseReturnRepository
from app.repositories.supplier_refund import SupplierRefundRepository
from app.schemas.supplier_refund import (
    SupplierRefundConfirm,
    SupplierRefundCreate,
    SupplierRefundFail,
    SupplierRefundListOut,
    SupplierRefundRecordOut,
)
from app.services.authorization import AuthorizationService
from app.services.observability import emit_event
from app.services.purchase_return_state import require_transition

_UNAVAILABLE = "供应商退款记录不存在或不可访问"
_ZERO = Decimal("0")


class SupplierRefundService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.refunds = SupplierRefundRepository(session, context.tenant_id)
        self.returns = PurchaseReturnRepository(session, context.tenant_id)

    def list_refunds(
        self,
        *,
        q: str | None,
        purchase_return_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> SupplierRefundListOut:
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_REFUND_READ,))
        rows, total = self.refunds.list_page(
            q=q,
            purchase_return_id=purchase_return_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            SupplierRefundRecordOut(
                id=record.id,
                refund_no=record.refund_no or "",
                purchase_return_id=record.purchase_return_id,
                purchase_return_no=return_no or "",
                purchase_order_id=int(order_id or 0),
                purchase_order_no=order_no or "",
                supplier_id=int(supplier_id or 0),
                supplier_name=supplier_name or "",
                amount=float(record.amount),
                status=record.status,
                external_reference_no=record.external_reference_no,
                failure_reason=record.failure_reason,
                received_at=record.received_at,
                created_by=record.created_by,
                created_by_name=created_name,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for (
                record,
                return_no,
                order_id,
                order_no,
                supplier_id,
                supplier_name,
                created_name,
            ) in rows
        ]
        return SupplierRefundListOut(items=items, total=total, page=page, page_size=page_size)

    def get_refund(self, refund_id: int) -> SupplierRefundRecordOut:
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_REFUND_READ,))
        record = self.refunds.get_in_tenant(refund_id)
        if record is None:
            raise AppError(_UNAVAILABLE, code=40502, status_code=404)
        return self._out(record)

    def create_refund(
        self, return_id: int, payload: SupplierRefundCreate
    ) -> SupplierRefundRecordOut:
        """创建一条待确认供应商退款。失败历史不能覆盖，每次尝试都是新行。不改库存。"""
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_REFUND_CREATE,))
        try:
            record = self.returns.get_for_update(return_id)
            if record is None:
                raise AppError("采购退货单不存在或不可访问", code=40500, status_code=404)
            if record.settlement_type == PurchaseReturnSettlementType.NO_REFUND.value:
                raise AppError(
                    "无退款采购退货不创建供应商退款",
                    code=40357,
                    status_code=400,
                    data={"error": "SUPPLIER_REFUND_NOT_ALLOWED"},
                )
            if record.status != PurchaseReturnStatus.WAITING_REFUND.value:
                raise AppError(
                    "采购退货尚未进入待退款，不能创建供应商退款",
                    code=40357,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_REFUND_NOT_READY"},
                )
            if self.refunds.has_pending(return_id):
                raise AppError(
                    "已有待确认供应商退款，请先确认或标记失败",
                    code=40359,
                    status_code=400,
                    data={"error": "SUPPLIER_REFUND_PENDING_EXISTS"},
                )
            remaining = self._remaining(record)
            amount = payload.amount if payload.amount is not None else remaining
            if amount <= 0:
                raise AppError(
                    "没有剩余可退金额",
                    code=40358,
                    status_code=400,
                    data={"error": "SUPPLIER_REFUND_EXCEEDS_APPROVED"},
                )
            if amount > remaining:
                raise AppError(
                    "退款金额超过批准剩余可退金额",
                    code=40358,
                    status_code=400,
                    data={"error": "SUPPLIER_REFUND_EXCEEDS_APPROVED"},
                )
            refund = SupplierRefundRecord(
                tenant_id=self.context.tenant_id,
                purchase_return_id=return_id,
                amount=amount,
                status=SupplierRefundRecordStatus.PENDING.value,
                external_reference_no=payload.external_reference_no,
                created_by=self.context.user_id,
            )
            self.refunds.add(refund)
            self.session.flush()
            refund.refund_no = f"SRF{datetime.now().year}{refund.id:06d}"
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.refunds.get_in_tenant(refund.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40502, status_code=404)
        return self._out(created)

    def confirm_supplier_refund(
        self, refund_id: int, payload: SupplierRefundConfirm
    ) -> SupplierRefundRecordOut:
        """人工确认供应商退款已到账。不修改 Inventory。全部退款后采购退货 COMPLETED。

        核心流程：
        1. 锁退款记录。
        2. 已 SUCCESS 则拒绝，避免重复累计。
        3. 锁 PurchaseReturn，校验剩余可退。
        4. 记录 → SUCCESS，更新 refund_status。
        5. 成功金额达到批准金额且货已出完 → COMPLETED。
        """
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_REFUND_CONFIRM,))
        try:
            refund = self.refunds.get_for_update(refund_id)
            if refund is None:
                raise AppError(_UNAVAILABLE, code=40502, status_code=404)
            if refund.status == SupplierRefundRecordStatus.SUCCESS.value:
                raise AppError(
                    "供应商退款已经成功，不能重复确认",
                    code=40360,
                    status_code=400,
                    data={"error": "SUPPLIER_REFUND_ALREADY_SUCCESS"},
                )
            if refund.status != SupplierRefundRecordStatus.PENDING.value:
                raise AppError(
                    "只有待确认的供应商退款可以标记成功",
                    code=40361,
                    status_code=400,
                    data={"error": "SUPPLIER_REFUND_ALREADY_FINAL"},
                )
            record = self.returns.get_for_update(refund.purchase_return_id)
            if record is None:
                raise AppError("采购退货单不存在或不可访问", code=40500, status_code=404)
            refund.status = SupplierRefundRecordStatus.SUCCESS.value
            refund.received_at = payload.received_at or datetime.now()
            if payload.external_reference_no:
                refund.external_reference_no = payload.external_reference_no
            remaining = self._remaining(record)
            if remaining <= refund.amount:
                record.refund_status = PurchaseReturnRefundStatus.SUCCESS.value
                if self._goods_fully_returned(record):
                    require_transition(record.status, PurchaseReturnStatus.COMPLETED.value)
                    record.status = PurchaseReturnStatus.COMPLETED.value
                    record.completed_at = datetime.now()
                    emit_event(
                        self.session,
                        self.context,
                        event_type=EventType.PURCHASE_RETURN_COMPLETED,
                        aggregate_type=AggregateType.PURCHASE_RETURN,
                        aggregate_id=record.id,
                        payload={"purchase_return_no": record.purchase_return_no},
                    )
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_refund(refund_id)

    def fail_refund(self, refund_id: int, payload: SupplierRefundFail) -> SupplierRefundRecordOut:
        """标记供应商退款失败。失败记录保留，可以再创建新的退款行。不改库存。"""
        self.auth.require_all(self.context, (PermissionCode.SUPPLIER_REFUND_CONFIRM,))
        try:
            refund = self.refunds.get_for_update(refund_id)
            if refund is None:
                raise AppError(_UNAVAILABLE, code=40502, status_code=404)
            if refund.status == SupplierRefundRecordStatus.SUCCESS.value:
                raise AppError(
                    "已成功的供应商退款不能改成失败",
                    code=40360,
                    status_code=400,
                    data={"error": "SUPPLIER_REFUND_ALREADY_SUCCESS"},
                )
            if refund.status != SupplierRefundRecordStatus.PENDING.value:
                raise AppError(
                    "只有待确认的供应商退款可以标记失败",
                    code=40361,
                    status_code=400,
                    data={"error": "SUPPLIER_REFUND_ALREADY_FINAL"},
                )
            refund.status = SupplierRefundRecordStatus.FAILED.value
            refund.failure_reason = payload.failure_reason
            record = self.returns.get_for_update(refund.purchase_return_id)
            if record is not None:
                record.status = PurchaseReturnStatus.WAITING_REFUND.value
                record.refund_status = PurchaseReturnRefundStatus.PENDING.value
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_refund(refund_id)

    def _remaining(self, record) -> Decimal:
        approved = record.approved_refund_amount or record.requested_refund_amount or _ZERO
        used = self.refunds.success_amount(record.id)
        used += self.refunds.pending_amount(record.id)
        leftover = approved - used
        return leftover if leftover > 0 else _ZERO

    def _goods_fully_returned(self, record) -> bool:
        items = self.returns.list_items(record.id)
        return all((item.approved_return_quantity or 0) <= item.returned_quantity for item in items)

    def _out(self, record: SupplierRefundRecord) -> SupplierRefundRecordOut:
        parent = self.returns.get_in_tenant(record.purchase_return_id)
        po = parent.purchase_order if parent is not None else None
        supplier = parent.supplier if parent is not None else None
        return SupplierRefundRecordOut(
            id=record.id,
            refund_no=record.refund_no or "",
            purchase_return_id=record.purchase_return_id,
            purchase_return_no=(parent.purchase_return_no or "") if parent is not None else "",
            purchase_order_id=parent.purchase_order_id if parent is not None else 0,
            purchase_order_no=(po.order_no or "") if po is not None else "",
            supplier_id=parent.supplier_id if parent is not None else 0,
            supplier_name=supplier.name if supplier is not None else "",
            amount=float(record.amount),
            status=record.status,
            external_reference_no=record.external_reference_no,
            failure_reason=record.failure_reason,
            received_at=record.received_at,
            created_by=record.created_by,
            created_by_name=self._user_name(record.created_by),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.session.scalar(select(User.display_name).where(User.id == user_id))
