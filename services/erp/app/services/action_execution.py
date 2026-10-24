from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.action_execution import ErpActionExecutionReceipt
from app.schemas.action_execution import ActionExecutionReceiptOut, ActionExecutionRequest
from app.schemas.purchase import PurchaseOrderCreate
from app.schemas.sales_order import SalesOrderCreate
from app.schemas.stock_transfer import StockTransferCreate
from app.services.authorization import AuthorizationService
from app.services.purchase import PurchaseOrderService
from app.services.sales_order import SalesOrderService
from app.services.stock_transfer import StockTransferService

_ROUTES = {
    "PURCHASE_ORDER_CREATE": (
        PurchaseOrderCreate,
        PurchaseOrderService,
        "create_order",
        "PURCHASE_ORDER",
        "order_no",
    ),
    "SALES_ORDER_CREATE": (
        SalesOrderCreate,
        SalesOrderService,
        "create_order",
        "SALES_ORDER",
        "order_no",
    ),
    "INVENTORY_TRANSFER_CREATE": (
        StockTransferCreate,
        StockTransferService,
        "create_transfer",
        "STOCK_TRANSFER",
        "transfer_no",
    ),
}
_PERMISSIONS = {
    "PURCHASE_ORDER_CREATE": PermissionCode.PURCHASE_CREATE,
    "SALES_ORDER_CREATE": PermissionCode.ORDER_CREATE,
    "INVENTORY_TRANSFER_CREATE": PermissionCode.STOCK_TRANSFER_CREATE,
}


class ActionExecutionService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context

    @staticmethod
    def payload_hash(payload: dict) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()

    @staticmethod
    def out(row: ErpActionExecutionReceipt) -> ActionExecutionReceiptOut:
        return ActionExecutionReceiptOut.model_validate(row, from_attributes=True)

    def get(self, execution_key: str) -> ActionExecutionReceiptOut:
        row = self.session.scalars(
            select(ErpActionExecutionReceipt).where(
                ErpActionExecutionReceipt.tenant_id == self.context.tenant_id,
                ErpActionExecutionReceipt.execution_key == execution_key,
            )
        ).first()
        if row is None:
            raise AppError("执行凭据不存在", code=40482, status_code=404)
        AuthorizationService(self.session).require_all(
            self.context, (_PERMISSIONS[row.action_type],)
        )
        return self.out(row)

    def get_internal(self, execution_key: str) -> ActionExecutionReceiptOut:
        """仅供已通过服务间 HMAC 的内部路由读取幂等 Receipt。"""
        row = self.session.scalars(
            select(ErpActionExecutionReceipt).where(
                ErpActionExecutionReceipt.tenant_id == self.context.tenant_id,
                ErpActionExecutionReceipt.execution_key == execution_key,
            )
        ).first()
        if row is None:
            raise AppError("执行凭据不存在", code=40482, status_code=404)
        return self.out(row)

    def execute(self, request: ActionExecutionRequest) -> ActionExecutionReceiptOut:
        """先占用幂等键，再在同一事务创建业务草稿与成功 Receipt。"""
        actual_hash = self.payload_hash(request.payload)
        if actual_hash != request.payload_hash:
            raise AppError("执行参数摘要不匹配", code=40982, status_code=409)
        existing = self.session.scalars(
            select(ErpActionExecutionReceipt).where(
                ErpActionExecutionReceipt.tenant_id == self.context.tenant_id,
                ErpActionExecutionReceipt.execution_key == request.execution_key,
            )
        ).first()
        if existing is not None:
            if existing.payload_hash != actual_hash or existing.action_type != request.action_type:
                raise AppError("执行幂等键已用于其他参数", code=40983, status_code=409)
            return self.out(existing)

        try:
            receipt = ErpActionExecutionReceipt(
                tenant_id=self.context.tenant_id,
                execution_key=request.execution_key,
                action_type=request.action_type,
                payload_hash=actual_hash,
                proposal_revision=request.proposal_revision,
                status="EXECUTING",
                created_by=self.context.user_id,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
            self.session.add(receipt)
            self.session.flush()
            schema, service_cls, method_name, resource_type, number_field = _ROUTES[
                request.action_type
            ]
            payload = schema.model_validate(request.payload)
            service = service_cls(self.session, self.context)
            preview = service.preview_create(payload)
            if not preview.valid:
                raise AppError(
                    "ERP 执行前业务条件已变化",
                    code=40984,
                    status_code=409,
                    data={
                        "blocking_errors": [item.model_dump() for item in preview.blocking_errors]
                    },
                )
            result = getattr(service, method_name)(payload, commit=False)
            receipt.status = "SUCCEEDED"
            receipt.resource_type = resource_type
            receipt.resource_id = result.id
            receipt.resource_no = getattr(result, number_field)
            receipt.completed_at = datetime.now(UTC).replace(tzinfo=None)
            self.session.commit()
            return self.out(receipt)
        except IntegrityError:
            self.session.rollback()
            raced = self.session.scalars(
                select(ErpActionExecutionReceipt).where(
                    ErpActionExecutionReceipt.tenant_id == self.context.tenant_id,
                    ErpActionExecutionReceipt.execution_key == request.execution_key,
                )
            ).first()
            if raced is not None and raced.payload_hash == actual_hash:
                return self.out(raced)
            raise AppError("执行幂等冲突", code=40983, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
