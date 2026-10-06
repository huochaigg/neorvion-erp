from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    OrderAuditContext,
    OrderCancelContext,
    OrderCreateContext,
    OrderReadContext,
    OrderSubmitContext,
    OrderUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.sales_order import (
    SalesOrderCancel,
    SalesOrderCreate,
    SalesOrderDetailOut,
    SalesOrderListOut,
    SalesOrderUpdate,
)
from app.services.sales_order import SalesOrderService

router = APIRouter(prefix="/sales-orders", tags=["sales-orders"])


@router.get("", response_model=ApiResponse[SalesOrderListOut], summary="销售订单列表")
def list_sales_orders(
    context: OrderReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    order_no: str | None = Query(default=None, max_length=32),
    external_order_no: str | None = Query(default=None, max_length=64),
    customer_id: int | None = Query(default=None, gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
    sku_code: str | None = Query(default=None, max_length=64),
    product_name: str | None = Query(default=None, max_length=128),
    status: str | None = Query(default=None, max_length=32),
    source: str | None = Query(default=None, max_length=16),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[SalesOrderListOut]:
    return ok(
        SalesOrderService(session, context).list_orders(
            q=q,
            order_no=order_no,
            external_order_no=external_order_no,
            customer_id=customer_id,
            warehouse_id=warehouse_id,
            sku_code=sku_code,
            product_name=product_name,
            status=status,
            source=source,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
    )


@router.post("", response_model=ApiResponse[SalesOrderDetailOut], summary="创建销售订单")
def create_sales_order(
    payload: SalesOrderCreate,
    context: OrderCreateContext,
    session: DbSession,
) -> ApiResponse[SalesOrderDetailOut]:
    return ok(SalesOrderService(session, context).create_order(payload), "创建成功")


@router.get(
    "/{order_id}",
    response_model=ApiResponse[SalesOrderDetailOut],
    summary="销售订单详情",
)
def get_sales_order(
    order_id: int,
    context: OrderReadContext,
    session: DbSession,
) -> ApiResponse[SalesOrderDetailOut]:
    return ok(SalesOrderService(session, context).get_order(order_id))


@router.patch(
    "/{order_id}",
    response_model=ApiResponse[SalesOrderDetailOut],
    summary="编辑销售订单",
)
def update_sales_order(
    order_id: int,
    payload: SalesOrderUpdate,
    context: OrderUpdateContext,
    session: DbSession,
) -> ApiResponse[SalesOrderDetailOut]:
    return ok(SalesOrderService(session, context).update_order(order_id, payload))


@router.post(
    "/{order_id}/submit",
    response_model=ApiResponse[SalesOrderDetailOut],
    summary="提交销售订单",
)
def submit_sales_order(
    order_id: int,
    context: OrderSubmitContext,
    session: DbSession,
) -> ApiResponse[SalesOrderDetailOut]:
    return ok(SalesOrderService(session, context).submit_order(order_id), "已提交")


@router.post(
    "/{order_id}/confirm",
    response_model=ApiResponse[SalesOrderDetailOut],
    summary="确认销售订单并预占库存",
)
def confirm_sales_order(
    order_id: int,
    context: OrderAuditContext,
    session: DbSession,
) -> ApiResponse[SalesOrderDetailOut]:
    return ok(
        SalesOrderService(session, context).confirm_order(order_id),
        "已确认并预占库存",
    )


@router.post(
    "/{order_id}/cancel",
    response_model=ApiResponse[SalesOrderDetailOut],
    summary="取消销售订单",
)
def cancel_sales_order(
    order_id: int,
    payload: SalesOrderCancel,
    context: OrderCancelContext,
    session: DbSession,
) -> ApiResponse[SalesOrderDetailOut]:
    return ok(SalesOrderService(session, context).cancel_order(order_id, payload), "已取消")
