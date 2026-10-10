from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    StockTransferCancelContext,
    StockTransferCreateContext,
    StockTransferOutboundContext,
    StockTransferReadContext,
    StockTransferReceiveContext,
    StockTransferSubmitContext,
    StockTransferUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.stock_transfer import (
    StockTransferCreate,
    StockTransferListOut,
    StockTransferOut,
    StockTransferUpdate,
)
from app.services.stock_transfer import StockTransferService

router = APIRouter(prefix="/stock-transfers", tags=["stock-transfers"])


@router.get("", response_model=ApiResponse[StockTransferListOut], summary="调拨单列表")
def list_stock_transfers(
    context: StockTransferReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    source_warehouse_id: int | None = Query(default=None, gt=0),
    target_warehouse_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=24),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[StockTransferListOut]:
    data = StockTransferService(session, context).list_transfers(
        q=(q or "").strip() or None,
        source_warehouse_id=source_warehouse_id,
        target_warehouse_id=target_warehouse_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.post("", response_model=ApiResponse[StockTransferOut], summary="创建调拨草稿")
def create_stock_transfer(
    payload: StockTransferCreate,
    context: StockTransferCreateContext,
    session: DbSession,
) -> ApiResponse[StockTransferOut]:
    return ok(StockTransferService(session, context).create_transfer(payload))


@router.get("/{transfer_id}", response_model=ApiResponse[StockTransferOut], summary="调拨单详情")
def get_stock_transfer(
    transfer_id: int,
    context: StockTransferReadContext,
    session: DbSession,
) -> ApiResponse[StockTransferOut]:
    return ok(StockTransferService(session, context).get_transfer(transfer_id))


@router.patch(
    "/{transfer_id}",
    response_model=ApiResponse[StockTransferOut],
    summary="编辑调拨草稿",
)
def update_stock_transfer(
    transfer_id: int,
    payload: StockTransferUpdate,
    context: StockTransferUpdateContext,
    session: DbSession,
) -> ApiResponse[StockTransferOut]:
    return ok(StockTransferService(session, context).update_transfer(transfer_id, payload))


@router.post(
    "/{transfer_id}/submit",
    response_model=ApiResponse[StockTransferOut],
    summary="提交调拨",
)
def submit_stock_transfer(
    transfer_id: int,
    context: StockTransferSubmitContext,
    session: DbSession,
) -> ApiResponse[StockTransferOut]:
    return ok(StockTransferService(session, context).submit_transfer(transfer_id))


@router.post(
    "/{transfer_id}/confirm-outbound",
    response_model=ApiResponse[StockTransferOut],
    summary="确认调出",
)
def confirm_stock_transfer_outbound(
    transfer_id: int,
    context: StockTransferOutboundContext,
    session: DbSession,
) -> ApiResponse[StockTransferOut]:
    return ok(StockTransferService(session, context).confirm_outbound(transfer_id))


@router.post(
    "/{transfer_id}/confirm-receive",
    response_model=ApiResponse[StockTransferOut],
    summary="确认调入",
)
def confirm_stock_transfer_receive(
    transfer_id: int,
    context: StockTransferReceiveContext,
    session: DbSession,
) -> ApiResponse[StockTransferOut]:
    return ok(StockTransferService(session, context).confirm_receive(transfer_id))


@router.post(
    "/{transfer_id}/cancel",
    response_model=ApiResponse[StockTransferOut],
    summary="取消尚未调出的调拨单",
)
def cancel_stock_transfer(
    transfer_id: int,
    context: StockTransferCancelContext,
    session: DbSession,
) -> ApiResponse[StockTransferOut]:
    return ok(StockTransferService(session, context).cancel_transfer(transfer_id))
