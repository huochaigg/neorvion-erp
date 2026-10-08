from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    PurchaseReceiptCancelContext,
    PurchaseReceiptConfirmContext,
    PurchaseReceiptCreateContext,
    PurchaseReceiptReadContext,
    PurchaseReceiptUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.purchase_receipt import (
    PurchaseReceiptCreate,
    PurchaseReceiptListOut,
    PurchaseReceiptOut,
    PurchaseReceiptUpdate,
)
from app.services.purchase_receipt import PurchaseReceiptService

router = APIRouter(prefix="/purchase-receipts", tags=["purchase-receipts"])


@router.get("", response_model=ApiResponse[PurchaseReceiptListOut], summary="收货单列表")
def list_purchase_receipts(
    context: PurchaseReceiptReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    purchase_order_id: int | None = Query(default=None, gt=0),
    supplier_id: int | None = Query(default=None, gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=16),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[PurchaseReceiptListOut]:
    data = PurchaseReceiptService(session, context).list_receipts(
        q=(q or "").strip() or None,
        purchase_order_id=purchase_order_id,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.post("", response_model=ApiResponse[PurchaseReceiptOut], summary="创建收货单")
def create_purchase_receipt(
    payload: PurchaseReceiptCreate,
    context: PurchaseReceiptCreateContext,
    session: DbSession,
) -> ApiResponse[PurchaseReceiptOut]:
    return ok(PurchaseReceiptService(session, context).create_receipt(payload))


@router.get("/{receipt_id}", response_model=ApiResponse[PurchaseReceiptOut], summary="收货单详情")
def get_purchase_receipt(
    receipt_id: int,
    context: PurchaseReceiptReadContext,
    session: DbSession,
) -> ApiResponse[PurchaseReceiptOut]:
    return ok(PurchaseReceiptService(session, context).get_receipt(receipt_id))


@router.patch("/{receipt_id}", response_model=ApiResponse[PurchaseReceiptOut], summary="编辑收货单")
def update_purchase_receipt(
    receipt_id: int,
    payload: PurchaseReceiptUpdate,
    context: PurchaseReceiptUpdateContext,
    session: DbSession,
) -> ApiResponse[PurchaseReceiptOut]:
    return ok(PurchaseReceiptService(session, context).update_receipt(receipt_id, payload))


@router.post(
    "/{receipt_id}/confirm",
    response_model=ApiResponse[PurchaseReceiptOut],
    summary="确认收货并入库",
)
def confirm_purchase_receipt(
    receipt_id: int,
    context: PurchaseReceiptConfirmContext,
    session: DbSession,
) -> ApiResponse[PurchaseReceiptOut]:
    return ok(PurchaseReceiptService(session, context).confirm_receipt(receipt_id))


@router.post(
    "/{receipt_id}/cancel",
    response_model=ApiResponse[PurchaseReceiptOut],
    summary="作废草稿收货单",
)
def cancel_purchase_receipt(
    receipt_id: int,
    context: PurchaseReceiptCancelContext,
    session: DbSession,
) -> ApiResponse[PurchaseReceiptOut]:
    return ok(PurchaseReceiptService(session, context).cancel_receipt(receipt_id))
