from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    PurchaseAuditContext,
    PurchaseCancelContext,
    PurchaseCreateContext,
    PurchaseReadContext,
    PurchaseSubmitContext,
    PurchaseUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.purchase import (
    PurchaseOrderCancel,
    PurchaseOrderCreate,
    PurchaseOrderDetailOut,
    PurchaseOrderListOut,
    PurchaseOrderReject,
    PurchaseOrderUpdate,
)
from app.services.purchase import PurchaseOrderService

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


@router.get("", response_model=ApiResponse[PurchaseOrderListOut], summary="采购单列表")
def list_purchase_orders(
    context: PurchaseReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    supplier_id: int | None = Query(default=None, gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
    sku_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=24),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    expected_from: Annotated[date | None, Query()] = None,
    expected_to: Annotated[date | None, Query()] = None,
    created_by: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[PurchaseOrderListOut]:
    return ok(
        PurchaseOrderService(session, context).list_orders(
            q=q,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            expected_from=expected_from,
            expected_to=expected_to,
            created_by=created_by,
            page=page,
            page_size=page_size,
        )
    )


@router.post("", response_model=ApiResponse[PurchaseOrderDetailOut], summary="创建采购单")
def create_purchase_order(
    payload: PurchaseOrderCreate,
    context: PurchaseCreateContext,
    session: DbSession,
) -> ApiResponse[PurchaseOrderDetailOut]:
    return ok(PurchaseOrderService(session, context).create_order(payload), "创建成功")


@router.get(
    "/{order_id}",
    response_model=ApiResponse[PurchaseOrderDetailOut],
    summary="采购单详情",
)
def get_purchase_order(
    order_id: int,
    context: PurchaseReadContext,
    session: DbSession,
) -> ApiResponse[PurchaseOrderDetailOut]:
    return ok(PurchaseOrderService(session, context).get_order(order_id))


@router.patch(
    "/{order_id}",
    response_model=ApiResponse[PurchaseOrderDetailOut],
    summary="编辑采购单",
)
def update_purchase_order(
    order_id: int,
    payload: PurchaseOrderUpdate,
    context: PurchaseUpdateContext,
    session: DbSession,
) -> ApiResponse[PurchaseOrderDetailOut]:
    return ok(PurchaseOrderService(session, context).update_order(order_id, payload))


@router.post(
    "/{order_id}/submit",
    response_model=ApiResponse[PurchaseOrderDetailOut],
    summary="提交审核",
)
def submit_purchase_order(
    order_id: int,
    context: PurchaseSubmitContext,
    session: DbSession,
) -> ApiResponse[PurchaseOrderDetailOut]:
    return ok(PurchaseOrderService(session, context).submit_order(order_id), "已提交审核")


@router.post(
    "/{order_id}/approve",
    response_model=ApiResponse[PurchaseOrderDetailOut],
    summary="审核通过",
)
def approve_purchase_order(
    order_id: int,
    context: PurchaseAuditContext,
    session: DbSession,
) -> ApiResponse[PurchaseOrderDetailOut]:
    return ok(
        PurchaseOrderService(session, context).approve_order(order_id),
        "审核通过，进入待收货",
    )


@router.post(
    "/{order_id}/reject",
    response_model=ApiResponse[PurchaseOrderDetailOut],
    summary="审核驳回",
)
def reject_purchase_order(
    order_id: int,
    payload: PurchaseOrderReject,
    context: PurchaseAuditContext,
    session: DbSession,
) -> ApiResponse[PurchaseOrderDetailOut]:
    return ok(PurchaseOrderService(session, context).reject_order(order_id, payload), "已驳回")


@router.post(
    "/{order_id}/cancel",
    response_model=ApiResponse[PurchaseOrderDetailOut],
    summary="取消采购单",
)
def cancel_purchase_order(
    order_id: int,
    payload: PurchaseOrderCancel,
    context: PurchaseCancelContext,
    session: DbSession,
) -> ApiResponse[PurchaseOrderDetailOut]:
    return ok(PurchaseOrderService(session, context).cancel_order(order_id, payload), "已取消")
