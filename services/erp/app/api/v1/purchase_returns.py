from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    PurchaseReturnApproveContext,
    PurchaseReturnCancelContext,
    PurchaseReturnCreateContext,
    PurchaseReturnOutboundContext,
    PurchaseReturnReadContext,
    PurchaseReturnRejectContext,
    PurchaseReturnSubmitContext,
    PurchaseReturnUpdateContext,
    SupplierRefundCreateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.purchase_return import (
    PurchaseReturnApprove,
    PurchaseReturnCreate,
    PurchaseReturnListOut,
    PurchaseReturnOut,
    PurchaseReturnPreviewOut,
    PurchaseReturnReject,
    PurchaseReturnUpdate,
)
from app.schemas.purchase_return_outbound import (
    PurchaseReturnOutboundCreate,
    PurchaseReturnOutboundOut,
)
from app.schemas.supplier_refund import SupplierRefundCreate, SupplierRefundRecordOut
from app.services.purchase_return import PurchaseReturnService
from app.services.purchase_return_outbound import PurchaseReturnOutboundService
from app.services.supplier_refund import SupplierRefundService

router = APIRouter(prefix="/purchase-returns", tags=["purchase-returns"])


@router.get("", response_model=ApiResponse[PurchaseReturnListOut], summary="采购退货列表")
def list_purchase_returns(
    context: PurchaseReturnReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    purchase_order_id: int | None = Query(default=None, gt=0),
    supplier_id: int | None = Query(default=None, gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
    sku_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=24),
    settlement_type: str | None = Query(default=None, max_length=16),
    refund_status: str | None = Query(default=None, max_length=16),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[PurchaseReturnListOut]:
    data = PurchaseReturnService(session, context).list_returns(
        q=(q or "").strip() or None,
        purchase_order_id=purchase_order_id,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        sku_id=sku_id,
        status=status,
        settlement_type=(settlement_type or "").strip().upper() or None,
        refund_status=refund_status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.get(
    "/preview",
    response_model=ApiResponse[PurchaseReturnPreviewOut],
    summary="创建采购退货前的可退数量预览",
)
def preview_purchase_return(
    context: PurchaseReturnReadContext,
    session: DbSession,
    purchase_order_id: int = Query(gt=0),
    warehouse_id: int | None = Query(default=None, gt=0),
) -> ApiResponse[PurchaseReturnPreviewOut]:
    return ok(PurchaseReturnService(session, context).preview(purchase_order_id, warehouse_id))


@router.post("", response_model=ApiResponse[PurchaseReturnOut], summary="创建采购退货草稿")
def create_purchase_return(
    payload: PurchaseReturnCreate,
    context: PurchaseReturnCreateContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOut]:
    return ok(PurchaseReturnService(session, context).create_purchase_return(payload))


@router.get("/{return_id}", response_model=ApiResponse[PurchaseReturnOut], summary="采购退货详情")
def get_purchase_return(
    return_id: int,
    context: PurchaseReturnReadContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOut]:
    return ok(PurchaseReturnService(session, context).get_return(return_id))


@router.patch(
    "/{return_id}",
    response_model=ApiResponse[PurchaseReturnOut],
    summary="编辑采购退货草稿",
)
def update_purchase_return(
    return_id: int,
    payload: PurchaseReturnUpdate,
    context: PurchaseReturnUpdateContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOut]:
    return ok(PurchaseReturnService(session, context).update_purchase_return(return_id, payload))


@router.post(
    "/{return_id}/submit",
    response_model=ApiResponse[PurchaseReturnOut],
    summary="提交采购退货",
)
def submit_purchase_return(
    return_id: int,
    context: PurchaseReturnSubmitContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOut]:
    return ok(PurchaseReturnService(session, context).submit_purchase_return(return_id))


@router.post(
    "/{return_id}/approve",
    response_model=ApiResponse[PurchaseReturnOut],
    summary="审核通过采购退货",
)
def approve_purchase_return(
    return_id: int,
    payload: PurchaseReturnApprove,
    context: PurchaseReturnApproveContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOut]:
    return ok(PurchaseReturnService(session, context).approve_purchase_return(return_id, payload))


@router.post(
    "/{return_id}/reject",
    response_model=ApiResponse[PurchaseReturnOut],
    summary="拒绝采购退货",
)
def reject_purchase_return(
    return_id: int,
    payload: PurchaseReturnReject,
    context: PurchaseReturnRejectContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOut]:
    return ok(PurchaseReturnService(session, context).reject_purchase_return(return_id, payload))


@router.post(
    "/{return_id}/cancel",
    response_model=ApiResponse[PurchaseReturnOut],
    summary="取消采购退货",
)
def cancel_purchase_return(
    return_id: int,
    context: PurchaseReturnCancelContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOut]:
    return ok(PurchaseReturnService(session, context).cancel_purchase_return(return_id))


@router.post(
    "/{return_id}/outbounds",
    response_model=ApiResponse[PurchaseReturnOutboundOut],
    summary="创建采购退货出库草稿",
)
def create_purchase_return_outbound(
    return_id: int,
    payload: PurchaseReturnOutboundCreate,
    context: PurchaseReturnOutboundContext,
    session: DbSession,
) -> ApiResponse[PurchaseReturnOutboundOut]:
    return ok(PurchaseReturnOutboundService(session, context).create_outbound(return_id, payload))


@router.post(
    "/{return_id}/refunds",
    response_model=ApiResponse[SupplierRefundRecordOut],
    summary="创建供应商退款记录",
)
def create_purchase_return_refund(
    return_id: int,
    payload: SupplierRefundCreate,
    context: SupplierRefundCreateContext,
    session: DbSession,
) -> ApiResponse[SupplierRefundRecordOut]:
    return ok(SupplierRefundService(session, context).create_refund(return_id, payload))
