from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    ShipmentCancelContext,
    ShipmentConfirmContext,
    ShipmentCreateContext,
    ShipmentDeliverContext,
    ShipmentReadContext,
    ShipmentTrackingContext,
    ShipmentUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentDeliver,
    ShipmentListOut,
    ShipmentOut,
    ShipmentUpdate,
    TrackingEventCreate,
    TrackingEventOut,
)
from app.services.shipment import ShipmentService

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.get("", response_model=ApiResponse[ShipmentListOut], summary="物流单列表")
def list_shipments(
    context: ShipmentReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    sales_order_id: int | None = Query(default=None, gt=0),
    outbound_order_id: int | None = Query(default=None, gt=0),
    carrier_id: int | None = Query(default=None, gt=0),
    customer_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=24),
    shipped_from: Annotated[datetime | None, Query()] = None,
    shipped_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[ShipmentListOut]:
    data = ShipmentService(session, context).list_shipments(
        q=(q or "").strip() or None,
        sales_order_id=sales_order_id,
        outbound_order_id=outbound_order_id,
        carrier_id=carrier_id,
        customer_id=customer_id,
        status=status,
        shipped_from=shipped_from,
        shipped_to=shipped_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.post("", response_model=ApiResponse[ShipmentOut], summary="创建物流单")
def create_shipment(
    payload: ShipmentCreate,
    context: ShipmentCreateContext,
    session: DbSession,
) -> ApiResponse[ShipmentOut]:
    return ok(ShipmentService(session, context).create_shipment(payload), "已保存物流草稿")


@router.get("/{shipment_id}", response_model=ApiResponse[ShipmentOut], summary="物流单详情")
def get_shipment(
    shipment_id: int,
    context: ShipmentReadContext,
    session: DbSession,
) -> ApiResponse[ShipmentOut]:
    return ok(ShipmentService(session, context).get_shipment(shipment_id))


@router.patch("/{shipment_id}", response_model=ApiResponse[ShipmentOut], summary="编辑物流单")
def update_shipment(
    shipment_id: int,
    payload: ShipmentUpdate,
    context: ShipmentUpdateContext,
    session: DbSession,
) -> ApiResponse[ShipmentOut]:
    return ok(ShipmentService(session, context).update_shipment(shipment_id, payload))


@router.post(
    "/{shipment_id}/confirm",
    response_model=ApiResponse[ShipmentOut],
    summary="确认发货",
)
def confirm_shipment(
    shipment_id: int,
    context: ShipmentConfirmContext,
    session: DbSession,
) -> ApiResponse[ShipmentOut]:
    return ok(ShipmentService(session, context).confirm_shipment(shipment_id), "已确认发货")


@router.post(
    "/{shipment_id}/cancel",
    response_model=ApiResponse[ShipmentOut],
    summary="取消物流单",
)
def cancel_shipment(
    shipment_id: int,
    context: ShipmentCancelContext,
    session: DbSession,
) -> ApiResponse[ShipmentOut]:
    return ok(ShipmentService(session, context).cancel_shipment(shipment_id), "已取消")


@router.get(
    "/{shipment_id}/tracking-events",
    response_model=ApiResponse[list[TrackingEventOut]],
    summary="物流轨迹",
)
def list_tracking_events(
    shipment_id: int,
    context: ShipmentReadContext,
    session: DbSession,
) -> ApiResponse[list[TrackingEventOut]]:
    return ok(ShipmentService(session, context).list_tracking_events(shipment_id))


@router.post(
    "/{shipment_id}/tracking-events",
    response_model=ApiResponse[ShipmentOut],
    summary="新增物流轨迹",
)
def add_tracking_event(
    shipment_id: int,
    payload: TrackingEventCreate,
    context: ShipmentTrackingContext,
    session: DbSession,
) -> ApiResponse[ShipmentOut]:
    return ok(ShipmentService(session, context).add_tracking_event(shipment_id, payload))


@router.post(
    "/{shipment_id}/deliver",
    response_model=ApiResponse[ShipmentOut],
    summary="确认签收",
)
def deliver_shipment(
    shipment_id: int,
    payload: ShipmentDeliver,
    context: ShipmentDeliverContext,
    session: DbSession,
) -> ApiResponse[ShipmentOut]:
    return ok(ShipmentService(session, context).mark_delivered(shipment_id, payload), "已签收")
