from fastapi import APIRouter

from app.api.deps import DbSession
from app.api.rbac_deps import OrderCreateContext, PurchaseCreateContext, StockTransferCreateContext
from app.schemas.action_preview import ActionPreviewOut
from app.schemas.common import ApiResponse, ok
from app.schemas.purchase import PurchaseOrderCreate
from app.schemas.sales_order import SalesOrderCreate
from app.schemas.stock_transfer import StockTransferCreate
from app.services.purchase import PurchaseOrderService
from app.services.sales_order import SalesOrderService
from app.services.stock_transfer import StockTransferService

router = APIRouter(prefix="/action-previews", tags=["action-previews"])


@router.post("/purchase-order", response_model=ApiResponse[ActionPreviewOut])
def preview_purchase_order(
    payload: PurchaseOrderCreate, context: PurchaseCreateContext, session: DbSession
):
    return ok(PurchaseOrderService(session, context).preview_create(payload))


@router.post("/sales-order", response_model=ApiResponse[ActionPreviewOut])
def preview_sales_order(payload: SalesOrderCreate, context: OrderCreateContext, session: DbSession):
    return ok(SalesOrderService(session, context).preview_create(payload))


@router.post("/inventory-transfer", response_model=ApiResponse[ActionPreviewOut])
def preview_inventory_transfer(
    payload: StockTransferCreate, context: StockTransferCreateContext, session: DbSession
):
    return ok(StockTransferService(session, context).preview_create(payload))
