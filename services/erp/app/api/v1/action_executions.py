from typing import Annotated

from fastapi import APIRouter, Header

from app.api.deps import CurrentTenant, DbSession
from app.api.rbac_deps import OrderCreateContext, PurchaseCreateContext, StockTransferCreateContext
from app.core.exceptions import AppError
from app.core.execution_auth import verify_execution_authorization, verify_receipt_authorization
from app.core.tenant import TenantContext
from app.db.session import open_tenant_session
from app.schemas.action_execution import ActionExecutionReceiptOut, ActionExecutionRequest
from app.schemas.common import ApiResponse, ok
from app.services.action_execution import ActionExecutionService

router = APIRouter(prefix="/action-executions", tags=["action-executions"])


def _execute(
    payload: ActionExecutionRequest,
    context: TenantContext,
    session: DbSession,
    signature: str,
    expires_at: str,
    expected_action_type: str,
) -> ApiResponse[ActionExecutionReceiptOut]:
    if payload.action_type != expected_action_type:
        raise AppError("执行动作与固定路由不匹配", code=40082, status_code=400)
    verify_execution_authorization(
        signature,
        expires_at,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        action_type=payload.action_type,
        execution_key=payload.execution_key,
        proposal_revision=payload.proposal_revision,
        payload_hash=payload.payload_hash,
    )
    return ok(ActionExecutionService(session, context).execute(payload), "ERP 业务草稿已创建")


@router.post("/purchase-order", response_model=ApiResponse[ActionExecutionReceiptOut])
def execute_purchase_order(
    payload: ActionExecutionRequest,
    context: PurchaseCreateContext,
    session: DbSession,
    signature: Annotated[str, Header(alias="X-Copilot-Execution-Signature")],
    expires_at: Annotated[str, Header(alias="X-Copilot-Execution-Expires")],
):
    return _execute(payload, context, session, signature, expires_at, "PURCHASE_ORDER_CREATE")


@router.post("/sales-order", response_model=ApiResponse[ActionExecutionReceiptOut])
def execute_sales_order(
    payload: ActionExecutionRequest,
    context: OrderCreateContext,
    session: DbSession,
    signature: Annotated[str, Header(alias="X-Copilot-Execution-Signature")],
    expires_at: Annotated[str, Header(alias="X-Copilot-Execution-Expires")],
):
    return _execute(payload, context, session, signature, expires_at, "SALES_ORDER_CREATE")


@router.post("/inventory-transfer", response_model=ApiResponse[ActionExecutionReceiptOut])
def execute_inventory_transfer(
    payload: ActionExecutionRequest,
    context: StockTransferCreateContext,
    session: DbSession,
    signature: Annotated[str, Header(alias="X-Copilot-Execution-Signature")],
    expires_at: Annotated[str, Header(alias="X-Copilot-Execution-Expires")],
):
    return _execute(payload, context, session, signature, expires_at, "INVENTORY_TRANSFER_CREATE")


@router.get("/{execution_key}", response_model=ApiResponse[ActionExecutionReceiptOut])
def get_execution_receipt(execution_key: str, context: CurrentTenant, session: DbSession):
    return ok(ActionExecutionService(session, context).get(execution_key))


@router.get(
    "/internal-receipts/{execution_key}", response_model=ApiResponse[ActionExecutionReceiptOut]
)
def get_internal_execution_receipt(
    execution_key: str,
    tenant_id: Annotated[int, Header(alias="X-Tenant-ID")],
    signature: Annotated[str, Header(alias="X-Copilot-Receipt-Signature")],
    expires_at: Annotated[str, Header(alias="X-Copilot-Receipt-Expires")],
):
    """供 Copilot Worker 对 UNKNOWN 做只读对账；HMAC 不赋予任何 ERP 写权限。"""
    verify_receipt_authorization(
        signature, expires_at, tenant_id=tenant_id, execution_key=execution_key
    )
    session = open_tenant_session(tenant_id)
    try:
        context = TenantContext(
            user_id=0,
            tenant_id=tenant_id,
            member_id=0,
            is_owner=False,
            role="SYSTEM",
            role_codes=("SYSTEM",),
            permission_codes=frozenset(),
            token_jti="system-reconcile",
            token_version=0,
            authz_version=0,
        )
        return ok(ActionExecutionService(session, context).get_internal(execution_key))
    finally:
        session.close()
