from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import PurchaseReturnOutboundContext, PurchaseReturnReadContext
from app.schemas.common import ApiResponse, ok
from app.schemas.purchase_return_outbound import (
    PurchaseReturnOutboundListOut,
    PurchaseReturnOutboundOut,
)
from app.services.purchase_return_outbound import PurchaseReturnOutboundService

router = APIRouter(prefix="/purchase-return-outbounds", tags=["purchase-return-outbounds"])


@router.get(
    "",
    response_model=ApiResponse[PurchaseReturnOutboundListOut],
    summary="采购退货出库单列表",
)
def list_purchase_return_outbounds(
    context: PurchaseReturnReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    purchase_return_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=16),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[PurchaseReturnOutboundListOut]:
    data = PurchaseReturnOutboundService(session, context).list_outbounds(
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
    "/{outbound_id}",
    response_model=ApiResponse[PurchaseReturnOutboundOut],
    summary="采购退货出库单详情",
)
def get_purchase_return_outbound(
    outbound_id: int,
    context: PurchaseReturnReadContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOutboundOut]:
    return ok(PurchaseReturnOutboundService(session, context).get_outbound(outbound_id))


@router.post(
    "/{outbound_id}/confirm",
    response_model=ApiResponse[PurchaseReturnOutboundOut],
    summary="确认采购退货出库",
)
def confirm_purchase_return_outbound(
    outbound_id: int,
    context: PurchaseReturnOutboundContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOutboundOut]:
    service = PurchaseReturnOutboundService(session, context)
    return ok(service.confirm_purchase_return_outbound(outbound_id))


@router.post(
    "/{outbound_id}/cancel",
    response_model=ApiResponse[PurchaseReturnOutboundOut],
    summary="取消未确认的退货出库草稿",
)
def cancel_purchase_return_outbound(
    outbound_id: int,
    context: PurchaseReturnOutboundContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOutboundOut]:
    return ok(PurchaseReturnOutboundService(session, context).cancel_outbound(outbound_id))
