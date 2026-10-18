"""退款记录。V11 只做 ERP 内人工确认，不调用真实支付渠道。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import AggregateType, EventType
from app.core.exceptions import AppError
from app.core.identity_names import identity_display_name
from app.core.operations import OperationAction, OperationModule
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.after_sale import AfterSaleStatus, AfterSaleType, RefundStatus
from app.models.refund import RefundRecord, RefundRecordStatus
from app.repositories.after_sale import AfterSaleRepository
from app.repositories.refund import RefundRepository
from app.schemas.refund import (
    RefundConfirm,
    RefundCreate,
    RefundFail,
    RefundListOut,
    RefundRecordOut,
)
from app.services.authorization import AuthorizationService
from app.services.observability import emit_event, emit_operation

_UNAVAILABLE = "退款记录不存在或不可访问"
_ZERO = Decimal("0")


class RefundService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.refunds = RefundRepository(session, context.tenant_id)
        self.after_sales = AfterSaleRepository(session, context.tenant_id)

    def list_refunds(
        self,
        *,
        q: str | None,
        after_sale_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> RefundListOut:
        self.auth.require_all(self.context, (PermissionCode.REFUND_READ,))
        rows, total = self.refunds.list_page(
            q=q,
            after_sale_id=after_sale_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            RefundRecordOut(
                id=record.id,
                refund_no=record.refund_no or "",
                after_sale_order_id=record.after_sale_order_id,
                after_sale_no=after_sale_no or "",
                sales_order_id=int(sales_order_id or 0),
                sales_order_no=sales_no or "",
                customer_id=int(customer_id or 0),
                customer_name=customer_name or "",
                amount=float(record.amount),
                status=record.status,
                external_reference_no=record.external_reference_no,
                failure_reason=record.failure_reason,
                refunded_at=record.refunded_at,
                created_by=record.created_by,
                created_by_name=created_name,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for (
                record,
                after_sale_no,
                sales_order_id,
                sales_no,
                customer_id,
                customer_name,
                created_name,
            ) in rows
        ]
        return RefundListOut(items=items, total=total, page=page, page_size=page_size)

    def get_refund(self, refund_id: int) -> RefundRecordOut:
        self.auth.require_all(self.context, (PermissionCode.REFUND_READ,))
        record = self.refunds.get_in_tenant(refund_id)
        if record is None:
            raise AppError(_UNAVAILABLE, code=40496, status_code=404)
        return self._out(record)

    def create_refund(self, after_sale_id: int, payload: RefundCreate) -> RefundRecordOut:
        """创建一条待确认退款记录。失败历史不能覆盖，每次尝试都是新行。"""
        self.auth.require_all(self.context, (PermissionCode.REFUND_CREATE,))
        try:
            after_sale = self.after_sales.get_for_update(after_sale_id)
            if after_sale is None:
                raise AppError("售后单不存在或不可访问", code=40494, status_code=404)
            if after_sale.type == AfterSaleType.RETURN_ONLY.value:
                raise AppError(
                    "仅退货售后不创建退款",
                    code=40330,
                    status_code=400,
                    data={"error": "REFUND_NOT_ALLOWED"},
                )
            if after_sale.status != AfterSaleStatus.WAITING_REFUND.value:
                raise AppError(
                    "售后尚未进入待退款，不能创建退款记录",
                    code=40313,
                    status_code=400,
                    data={"error": "AFTER_SALE_RETURN_NOT_READY"},
                )
            if self.refunds.has_pending(after_sale_id):
                raise AppError(
                    "已有待确认退款，请先确认或标记失败",
                    code=40333,
                    status_code=400,
                    data={"error": "REFUND_PENDING_EXISTS"},
                )
            remaining = self._remaining(after_sale)
            amount = payload.amount if payload.amount is not None else remaining
            if amount <= 0:
                raise AppError(
                    "没有剩余可退金额",
                    code=40331,
                    status_code=400,
                    data={"error": "REFUND_EXCEEDS_APPROVED"},
                )
            if amount > remaining:
                raise AppError(
                    "退款金额超过批准剩余可退金额",
                    code=40331,
                    status_code=400,
                    data={"error": "REFUND_EXCEEDS_APPROVED"},
                )
            record = RefundRecord(
                tenant_id=self.context.tenant_id,
                after_sale_order_id=after_sale_id,
                amount=amount,
                status=RefundRecordStatus.PENDING.value,
                external_reference_no=payload.external_reference_no,
                created_by=self.context.user_id,
            )
            self.refunds.add(record)
            self.session.flush()
            record.refund_no = f"RF{datetime.now().year}{record.id:06d}"
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.refunds.get_in_tenant(record.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40496, status_code=404)
        return self._out(created)

    def confirm_refund(self, refund_id: int, payload: RefundConfirm) -> RefundRecordOut:
        """人工确认外部退款已完成。成功后售后进入 COMPLETED。"""
        self.auth.require_all(self.context, (PermissionCode.REFUND_CONFIRM,))
        try:
            record = self.refunds.get_for_update(refund_id)
            if record is None:
                raise AppError(_UNAVAILABLE, code=40496, status_code=404)
            if record.status == RefundRecordStatus.SUCCESS.value:
                raise AppError(
                    "退款已经成功，不能重复确认",
                    code=40332,
                    status_code=400,
                    data={"error": "REFUND_ALREADY_SUCCESS"},
                )
            if record.status != RefundRecordStatus.PENDING.value:
                raise AppError(
                    "只有待确认的退款可以标记成功",
                    code=40334,
                    status_code=400,
                    data={"error": "REFUND_ALREADY_FINAL"},
                )
            after_sale = self.after_sales.get_for_update(record.after_sale_order_id)
            if after_sale is None:
                raise AppError("售后单不存在或不可访问", code=40494, status_code=404)
            record.status = RefundRecordStatus.SUCCESS.value
            record.refunded_at = payload.refunded_at or datetime.now()
            if payload.external_reference_no:
                record.external_reference_no = payload.external_reference_no
            remaining = self._remaining(after_sale)
            # SUCCESS 金额已占用 remaining 计算里的 pending；确认后 pending 变 success。
            if remaining <= record.amount:
                after_sale.refund_status = RefundStatus.SUCCESS.value
                after_sale.status = AfterSaleStatus.COMPLETED.value
                after_sale.completed_at = datetime.now()
                emit_event(
                    self.session,
                    self.context,
                    event_type=EventType.AFTER_SALE_COMPLETED,
                    aggregate_type=AggregateType.AFTER_SALE,
                    aggregate_id=after_sale.id,
                    reference_type="SALES_ORDER",
                    reference_id=after_sale.sales_order_id,
                    payload={"after_sale_no": after_sale.after_sale_no},
                )
            emit_event(
                self.session,
                self.context,
                event_type=EventType.REFUND_SUCCESS,
                aggregate_type=AggregateType.REFUND,
                aggregate_id=record.id,
                reference_type="AFTER_SALE",
                reference_id=after_sale.id,
                payload={"refund_no": record.refund_no, "amount": str(record.amount)},
            )
            emit_operation(
                self.session,
                self.context,
                action=OperationAction.CONFIRM.value,
                module=OperationModule.REFUND.value,
                resource_type="REFUND",
                resource_id=record.id,
                resource_name=record.refund_no,
                description="确认售后退款成功",
            )
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_refund(refund_id)

    def fail_refund(self, refund_id: int, payload: RefundFail) -> RefundRecordOut:
        """标记退款失败。售后仍保持 WAITING_REFUND，可以再创建新的 RefundRecord。"""
        self.auth.require_all(self.context, (PermissionCode.REFUND_CONFIRM,))
        try:
            record = self.refunds.get_for_update(refund_id)
            if record is None:
                raise AppError(_UNAVAILABLE, code=40496, status_code=404)
            if record.status == RefundRecordStatus.SUCCESS.value:
                raise AppError(
                    "已成功的退款不能改成失败",
                    code=40332,
                    status_code=400,
                    data={"error": "REFUND_ALREADY_SUCCESS"},
                )
            if record.status != RefundRecordStatus.PENDING.value:
                raise AppError(
                    "只有待确认的退款可以标记失败",
                    code=40334,
                    status_code=400,
                    data={"error": "REFUND_ALREADY_FINAL"},
                )
            record.status = RefundRecordStatus.FAILED.value
            record.failure_reason = payload.failure_reason
            after_sale = self.after_sales.get_for_update(record.after_sale_order_id)
            if after_sale is not None:
                after_sale.status = AfterSaleStatus.WAITING_REFUND.value
                after_sale.refund_status = RefundStatus.PENDING.value
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_refund(refund_id)

    def _remaining(self, after_sale) -> Decimal:
        approved = after_sale.approved_refund_amount or after_sale.requested_refund_amount or _ZERO
        used = self.refunds.success_amount(after_sale.id)
        used += self.refunds.pending_amount(after_sale.id)
        leftover = approved - used
        return leftover if leftover > 0 else _ZERO

    def _out(self, record: RefundRecord) -> RefundRecordOut:
        after_sale = self.after_sales.get_in_tenant(record.after_sale_order_id)
        sales = after_sale.sales_order if after_sale is not None else None
        customer = after_sale.customer if after_sale is not None else None
        return RefundRecordOut(
            id=record.id,
            refund_no=record.refund_no or "",
            after_sale_order_id=record.after_sale_order_id,
            after_sale_no=(after_sale.after_sale_no or "") if after_sale is not None else "",
            sales_order_id=after_sale.sales_order_id if after_sale is not None else 0,
            sales_order_no=(sales.order_no or "") if sales is not None else "",
            customer_id=after_sale.customer_id if after_sale is not None else 0,
            customer_name=customer.name if customer is not None else "",
            amount=float(record.amount),
            status=record.status,
            external_reference_no=record.external_reference_no,
            failure_reason=record.failure_reason,
            refunded_at=record.refunded_at,
            created_by=record.created_by,
            created_by_name=self._user_name(record.created_by),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _user_name(self, user_id: int | None) -> str | None:
        return identity_display_name(self.session, user_id)
