from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    OutboundCancelContext,
    OutboundConfirmContext,
    OutboundCreateContext,
    OutboundPickContext,
    OutboundReadContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.outbound import (
    OutboundCreate,
    OutboundListOut,
    OutboundOrderOut,
    OutboundPick,
)
from app.services.outbound import OutboundOrderService

router = APIRouter(prefix="/outbound-orders", tags=["outbound-orders"])


@router.get("", response_model=ApiResponse[OutboundListOut], summary="出库单列表")
def list_outbound_orders(
    context: OutboundReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    sales_order_id: int | None = Query(default=None, gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=24),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[OutboundListOut]:
    data = OutboundOrderService(session, context).list_outbounds(
        q=(q or "").strip() or None,
        sales_order_id=sales_order_id,
        warehouse_id=warehouse_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.post("", response_model=ApiResponse[OutboundOrderOut], summary="创建出库单")
def create_outbound_order(
    payload: OutboundCreate,
    context: OutboundCreateContext,
    session: DbSession,
) -> ApiResponse[OutboundOrderOut]:
    return ok(OutboundOrderService(session, context).create_outbound(payload))


@router.get("/{outbound_id}", response_model=ApiResponse[OutboundOrderOut], summary="出库单详情")
def get_outbound_order(
    outbound_id: int,
    context: OutboundReadContext,
    session: DbSession,
) -> ApiResponse[OutboundOrderOut]:
    return ok(OutboundOrderService(session, context).get_outbound(outbound_id))


@router.post(
    "/{outbound_id}/pick",
    response_model=ApiResponse[OutboundOrderOut],
    summary="确认拣货",
)
def pick_outbound_order(
    outbound_id: int,
    payload: OutboundPick,
    context: OutboundPickContext,
    session: DbSession,
) -> ApiResponse[OutboundOrderOut]:
    return ok(OutboundOrderService(session, context).confirm_picking(outbound_id, payload))


@router.post(
    "/{outbound_id}/confirm",
    response_model=ApiResponse[OutboundOrderOut],
    summary="确认出库",
)
def confirm_outbound_order(
    outbound_id: int,
    context: OutboundConfirmContext,
    session: DbSession,
) -> ApiResponse[OutboundOrderOut]:
    return ok(OutboundOrderService(session, context).confirm_outbound(outbound_id))


@router.post(
    "/{outbound_id}/cancel",
    response_model=ApiResponse[OutboundOrderOut],
    summary="取消出库单",
)
def cancel_outbound_order(
    outbound_id: int,
    context: OutboundCancelContext,
    session: DbSession,
) -> ApiResponse[OutboundOrderOut]:
    return ok(OutboundOrderService(session, context).cancel_outbound(outbound_id))
