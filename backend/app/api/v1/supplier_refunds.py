from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import SupplierRefundConfirmContext, SupplierRefundReadContext
from app.schemas.common import ApiResponse, ok
from app.schemas.supplier_refund import (
    SupplierRefundConfirm,
    SupplierRefundFail,
    SupplierRefundListOut,
    SupplierRefundRecordOut,
)
from app.services.supplier_refund import SupplierRefundService

router = APIRouter(prefix="/supplier-refunds", tags=["supplier-refunds"])


@router.get("", response_model=ApiResponse[SupplierRefundListOut], summary="供应商退款列表")
def list_supplier_refunds(
    context: SupplierRefundReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    purchase_return_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=16),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[SupplierRefundListOut]:
    data = SupplierRefundService(session, context).list_refunds(
        q=(q or "").strip() or None,
        purchase_return_id=purchase_return_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.get(
    "/{refund_id}",
    response_model=ApiResponse[SupplierRefundRecordOut],
    summary="供应商退款详情",
)
def get_supplier_refund(
    refund_id: int,
    context: SupplierRefundReadContext,
    session: DbSession,
) -> ApiResponse[SupplierRefundRecordOut]:
    return ok(SupplierRefundService(session, context).get_refund(refund_id))


@router.post(
    "/{refund_id}/confirm",
    response_model=ApiResponse[SupplierRefundRecordOut],
    summary="确认供应商退款成功",
)
def confirm_supplier_refund(
    refund_id: int,
    payload: SupplierRefundConfirm,
    context: SupplierRefundConfirmContext,
    session: DbSession,
) -> ApiResponse[SupplierRefundRecordOut]:
    return ok(SupplierRefundService(session, context).confirm_supplier_refund(refund_id, payload))


@router.post(
    "/{refund_id}/fail",
    response_model=ApiResponse[SupplierRefundRecordOut],
    summary="标记供应商退款失败",
)
def fail_supplier_refund(
    refund_id: int,
    payload: SupplierRefundFail,
    context: SupplierRefundConfirmContext,
    session: DbSession,
) -> ApiResponse[SupplierRefundRecordOut]:
    return ok(SupplierRefundService(session, context).fail_refund(refund_id, payload))
