from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import RefundConfirmContext, RefundReadContext
from app.schemas.common import ApiResponse, ok
from app.schemas.refund import RefundConfirm, RefundFail, RefundListOut, RefundRecordOut
from app.services.refund import RefundService

router = APIRouter(prefix="/refunds", tags=["refunds"])


@router.get("", response_model=ApiResponse[RefundListOut], summary="退款记录列表")
def list_refunds(
    context: RefundReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    after_sale_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=16),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[RefundListOut]:
    data = RefundService(session, context).list_refunds(
        q=(q or "").strip() or None,
        after_sale_id=after_sale_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.get("/{refund_id}", response_model=ApiResponse[RefundRecordOut], summary="退款记录详情")
def get_refund(
    refund_id: int,
    context: RefundReadContext,
    session: DbSession,
) -> ApiResponse[RefundRecordOut]:
    return ok(RefundService(session, context).get_refund(refund_id))


@router.post(
    "/{refund_id}/confirm",
    response_model=ApiResponse[RefundRecordOut],
    summary="确认退款成功",
)
def confirm_refund(
    refund_id: int,
    payload: RefundConfirm,
    context: RefundConfirmContext,
    session: DbSession,
) -> ApiResponse[RefundRecordOut]:
    return ok(RefundService(session, context).confirm_refund(refund_id, payload))


@router.post(
    "/{refund_id}/fail",
    response_model=ApiResponse[RefundRecordOut],
    summary="标记退款失败",
)
def fail_refund(
    refund_id: int,
    payload: RefundFail,
    context: RefundConfirmContext,
    session: DbSession,
) -> ApiResponse[RefundRecordOut]:
    return ok(RefundService(session, context).fail_refund(refund_id, payload))
