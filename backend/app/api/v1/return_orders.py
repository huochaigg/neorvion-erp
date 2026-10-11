from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    ReturnOrderInboundContext,
    ReturnOrderReadContext,
    ReturnOrderReceiveContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.return_order import (
    ReturnOrderListOut,
    ReturnOrderOut,
    ReturnOrderUpdate,
    ReturnReceiveIn,
)
from app.services.return_order import ReturnOrderService

router = APIRouter(prefix="/return-orders", tags=["return-orders"])


@router.get("", response_model=ApiResponse[ReturnOrderListOut], summary="退货单列表")
def list_return_orders(
    context: ReturnOrderReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    after_sale_id: int | None = Query(default=None, gt=0),
    sales_order_id: int | None = Query(default=None, gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=24),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[ReturnOrderListOut]:
    data = ReturnOrderService(session, context).list_returns(
        q=(q or "").strip() or None,
        after_sale_id=after_sale_id,
        sales_order_id=sales_order_id,
        warehouse_id=warehouse_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.get("/{return_id}", response_model=ApiResponse[ReturnOrderOut], summary="退货单详情")
def get_return_order(
    return_id: int,
    context: ReturnOrderReadContext,
    session: DbSession,
) -> ApiResponse[ReturnOrderOut]:
    return ok(ReturnOrderService(session, context).get_return(return_id))


@router.patch(
    "/{return_id}",
    response_model=ApiResponse[ReturnOrderOut],
    summary="更新退货物流信息",
)
def update_return_order(
    return_id: int,
    payload: ReturnOrderUpdate,
    context: ReturnOrderReceiveContext,
    session: DbSession,
) -> ApiResponse[ReturnOrderOut]:
    return ok(ReturnOrderService(session, context).update_return(return_id, payload))


@router.post(
    "/{return_id}/receive",
    response_model=ApiResponse[ReturnOrderOut],
    summary="登记退货收货",
)
def receive_return_order(
    return_id: int,
    payload: ReturnReceiveIn,
    context: ReturnOrderReceiveContext,
    session: DbSession,
) -> ApiResponse[ReturnOrderOut]:
    return ok(ReturnOrderService(session, context).receive(return_id, payload))


@router.post(
    "/{return_id}/confirm-inbound",
    response_model=ApiResponse[ReturnOrderOut],
    summary="确认退货入库",
)
def confirm_return_inbound(
    return_id: int,
    context: ReturnOrderInboundContext,
    session: DbSession,
) -> ApiResponse[ReturnOrderOut]:
    return ok(ReturnOrderService(session, context).confirm_inbound(return_id))
