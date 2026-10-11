from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    AfterSaleApproveContext,
    AfterSaleCancelContext,
    AfterSaleCreateContext,
    AfterSaleReadContext,
    AfterSaleRejectContext,
    RefundCreateContext,
)
from app.schemas.after_sale import (
    AfterSaleApprove,
    AfterSaleCreate,
    AfterSaleListOut,
    AfterSaleOut,
    AfterSalePreviewOut,
    AfterSaleReject,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.refund import RefundCreate, RefundRecordOut
from app.services.after_sale import AfterSaleService
from app.services.refund import RefundService

router = APIRouter(prefix="/after-sales", tags=["after-sales"])


@router.get("", response_model=ApiResponse[AfterSaleListOut], summary="售后单列表")
def list_after_sales(
    context: AfterSaleReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    sales_order_id: int | None = Query(default=None, gt=0),
    customer_id: int | None = Query(default=None, gt=0),
    sku_code: str | None = Query(default=None, max_length=64),
    after_sale_type: str | None = Query(default=None, alias="type", max_length=24),
    status: str | None = Query(default=None, max_length=24),
    refund_status: str | None = Query(default=None, max_length=16),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[AfterSaleListOut]:
    data = AfterSaleService(session, context).list_after_sales(
        q=(q or "").strip() or None,
        sales_order_id=sales_order_id,
        customer_id=customer_id,
        sku_code=(sku_code or "").strip() or None,
        after_sale_type=(after_sale_type or "").strip().upper() or None,
        status=status,
        refund_status=refund_status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.get(
    "/preview",
    response_model=ApiResponse[AfterSalePreviewOut],
    summary="创建售后前的可退数量预览",
)
def preview_after_sale(
    context: AfterSaleReadContext,
    session: DbSession,
    sales_order_id: int = Query(gt=0),
) -> ApiResponse[AfterSalePreviewOut]:
    return ok(AfterSaleService(session, context).preview(sales_order_id))


@router.post("", response_model=ApiResponse[AfterSaleOut], summary="创建售后申请")
def create_after_sale(
    payload: AfterSaleCreate,
    context: AfterSaleCreateContext,
    session: DbSession,
) -> ApiResponse[AfterSaleOut]:
    return ok(AfterSaleService(session, context).create_after_sale(payload))


@router.get("/{after_sale_id}", response_model=ApiResponse[AfterSaleOut], summary="售后单详情")
def get_after_sale(
    after_sale_id: int,
    context: AfterSaleReadContext,
    session: DbSession,
) -> ApiResponse[AfterSaleOut]:
    return ok(AfterSaleService(session, context).get_after_sale(after_sale_id))


@router.post(
    "/{after_sale_id}/approve",
    response_model=ApiResponse[AfterSaleOut],
    summary="审核通过售后",
)
def approve_after_sale(
    after_sale_id: int,
    payload: AfterSaleApprove,
    context: AfterSaleApproveContext,
    session: DbSession,
) -> ApiResponse[AfterSaleOut]:
    return ok(AfterSaleService(session, context).approve_after_sale(after_sale_id, payload))


@router.post(
    "/{after_sale_id}/reject",
    response_model=ApiResponse[AfterSaleOut],
    summary="拒绝售后",
)
def reject_after_sale(
    after_sale_id: int,
    payload: AfterSaleReject,
    context: AfterSaleRejectContext,
    session: DbSession,
) -> ApiResponse[AfterSaleOut]:
    return ok(AfterSaleService(session, context).reject_after_sale(after_sale_id, payload))


@router.post(
    "/{after_sale_id}/cancel",
    response_model=ApiResponse[AfterSaleOut],
    summary="取消尚未审核的售后",
)
def cancel_after_sale(
    after_sale_id: int,
    context: AfterSaleCancelContext,
    session: DbSession,
) -> ApiResponse[AfterSaleOut]:
    return ok(AfterSaleService(session, context).cancel_after_sale(after_sale_id))


@router.post(
    "/{after_sale_id}/refunds",
    response_model=ApiResponse[RefundRecordOut],
    summary="创建退款记录",
)
def create_after_sale_refund(
    after_sale_id: int,
    payload: RefundCreate,
    context: RefundCreateContext,
    session: DbSession,
) -> ApiResponse[RefundRecordOut]:
    return ok(RefundService(session, context).create_refund(after_sale_id, payload))
