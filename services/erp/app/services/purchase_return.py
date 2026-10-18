"""采购退货。草稿不占用可退数量；提交审核后占用。不改原采购明细数量。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.purchase import PurchaseOrderItem, PurchaseOrderStatus
from app.models.purchase_return import (
    PurchaseReturn,
    PurchaseReturnItem,
    PurchaseReturnRefundStatus,
    PurchaseReturnSettlementType,
    PurchaseReturnStatus,
)
from app.models.user import User
from app.models.warehouse import WarehouseStatus
from app.repositories.inventory import InventoryRepository
from app.repositories.purchase import PurchaseOrderRepository
from app.repositories.purchase_return import PurchaseReturnRepository
from app.repositories.purchase_return_outbound import PurchaseReturnOutboundRepository
from app.repositories.supplier import SupplierRepository
from app.repositories.supplier_refund import SupplierRefundRepository
from app.repositories.warehouse import WarehouseRepository
from app.schemas.purchase_return import (
    PurchaseReturnApprove,
    PurchaseReturnCreate,
    PurchaseReturnItemIn,
    PurchaseReturnItemOut,
    PurchaseReturnListItem,
    PurchaseReturnListOut,
    PurchaseReturnOut,
    PurchaseReturnOutboundBriefOut,
    PurchaseReturnOutboundItemOut,
    PurchaseReturnPreviewItem,
    PurchaseReturnPreviewOut,
    PurchaseReturnReject,
    PurchaseReturnUpdate,
    SupplierRefundBriefOut,
)
from app.services.authorization import AuthorizationService
from app.services.purchase_return_state import (
    CANCELLABLE_STATUSES,
    EDITABLE_STATUSES,
    PENDING_APPROVAL,
    SUBMITTABLE_STATUSES,
    require_transition,
)

_UNAVAILABLE = "采购退货单不存在或不可访问"
_ELIGIBLE = {
    PurchaseOrderStatus.PARTIALLY_RECEIVED.value,
    PurchaseOrderStatus.RECEIVED.value,
}
_ZERO = Decimal("0")
_SETTLEMENT = {
    PurchaseReturnSettlementType.REFUND.value,
    PurchaseReturnSettlementType.NO_REFUND.value,
}


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


class PurchaseReturnService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.returns = PurchaseReturnRepository(session, context.tenant_id)
        self.outbounds = PurchaseReturnOutboundRepository(session, context.tenant_id)
        self.refunds = SupplierRefundRepository(session, context.tenant_id)
        self.orders = PurchaseOrderRepository(session, context.tenant_id)
        self.suppliers = SupplierRepository(session, context.tenant_id)
        self.warehouses = WarehouseRepository(session, context.tenant_id)
        self.inventories = InventoryRepository(session, context.tenant_id)

    def preview(
        self, purchase_order_id: int, warehouse_id: int | None = None
    ) -> PurchaseReturnPreviewOut:
        """创建采购退货前的可退数量 / 可退金额 / 当前仓库可用库存预览。"""
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_READ,))
        order = self.orders.get_in_tenant(purchase_order_id)
        if order is None:
            raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
        warehouse = order.warehouse
        chosen_id = warehouse_id or order.warehouse_id
        if warehouse_id is not None:
            chosen = self.warehouses.get_in_tenant(warehouse_id)
            if chosen is None:
                raise AppError("仓库不存在或不可访问", code=40440, status_code=404)
            warehouse = chosen
        items = self.orders.list_items(purchase_order_id)
        occupied_qty = self.returns.occupied_return_qty([row.id for row in items])
        occupied_amt = self.returns.occupied_refund_amount([row.id for row in items])
        returned_qty = self.returns.actual_returned_qty([row.id for row in items])
        stocks = {
            row.sku_id: row
            for row in self.inventories.list_by_warehouse_skus(
                chosen_id, [row.sku_id for row in items]
            )
        }
        preview_items: list[PurchaseReturnPreviewItem] = []
        for row in items:
            occ_qty = occupied_qty.get(row.id, 0)
            occ_amt = occupied_amt.get(row.id, _ZERO)
            returnable = max(row.received_quantity - occ_qty, 0)
            line_cap = self._line_refund_cap(row)
            refundable = line_cap - occ_amt
            if refundable < 0:
                refundable = _ZERO
            sku = row.sku
            product = sku.product if sku is not None else None
            spec = sku.spec_values if sku is not None and sku.spec_values else {}
            stock = stocks.get(row.sku_id)
            qty = stock.quantity if stock is not None else 0
            reserved = stock.reserved_quantity if stock is not None else 0
            preview_items.append(
                PurchaseReturnPreviewItem(
                    purchase_order_item_id=row.id,
                    sku_id=row.sku_id,
                    sku_code=(sku.sku_code or "") if sku is not None else "",
                    sku_name=sku.name if sku is not None else "",
                    product_name=product.name if product is not None else "",
                    spec_values=spec if isinstance(spec, dict) else {},
                    ordered_quantity=row.quantity,
                    received_quantity=row.received_quantity,
                    occupied_return_quantity=occ_qty,
                    returned_quantity=returned_qty.get(row.id, 0),
                    returnable_quantity=returnable,
                    unit_price=_money(row.unit_price),
                    occupied_refund_amount=float(occ_amt),
                    refundable_amount=float(refundable),
                    inventory_quantity=qty,
                    inventory_reserved=reserved,
                    inventory_available=max(qty - reserved, 0),
                )
            )
        return PurchaseReturnPreviewOut(
            purchase_order_id=order.id,
            purchase_order_no=order.order_no or "",
            supplier_id=order.supplier_id,
            supplier_name=order.supplier.name if order.supplier is not None else "",
            original_warehouse_id=order.warehouse_id,
            original_warehouse_name=order.warehouse.name if order.warehouse is not None else "",
            warehouse_id=chosen_id,
            warehouse_name=warehouse.name if warehouse is not None else "",
            status=order.status,
            eligible=order.status in _ELIGIBLE,
            items=preview_items,
        )

    def list_returns(
        self,
        *,
        q: str | None,
        purchase_order_id: int | None,
        supplier_id: int | None,
        warehouse_id: int | None,
        sku_id: int | None,
        status: str | None,
        settlement_type: str | None,
        refund_status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> PurchaseReturnListOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_READ,))
        rows, total = self.returns.list_page(
            q=q,
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            status=status,
            settlement_type=settlement_type,
            refund_status=refund_status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            PurchaseReturnListItem(
                id=order.id,
                purchase_return_no=order.purchase_return_no or "",
                purchase_order_id=order.purchase_order_id,
                purchase_order_no=order_no or "",
                supplier_id=order.supplier_id,
                supplier_name=supplier_name or "",
                warehouse_id=order.warehouse_id,
                warehouse_name=warehouse_name or "",
                sku_count=int(sku_count or 0),
                requested_return_quantity=int(req_qty or 0),
                approved_return_quantity=int(apr_qty) if apr_qty is not None else None,
                returned_quantity=int(ret_qty or 0),
                requested_refund_amount=float(order.requested_refund_amount),
                approved_refund_amount=_money(order.approved_refund_amount),
                status=order.status,
                settlement_type=order.settlement_type,
                refund_status=order.refund_status,
                created_at=order.created_at,
            )
            for (
                order,
                order_no,
                supplier_name,
                warehouse_name,
                sku_count,
                req_qty,
                apr_qty,
                ret_qty,
            ) in rows
        ]
        return PurchaseReturnListOut(items=items, total=total, page=page, page_size=page_size)

    def get_return(self, return_id: int) -> PurchaseReturnOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_READ,))
        order = self.returns.get_in_tenant(return_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40500, status_code=404)
        return self._out(order)

    def create_purchase_return(self, payload: PurchaseReturnCreate) -> PurchaseReturnOut:
        """创建采购退货草稿。不占用可退数量，不修改 Inventory，不改原采购明细。

        功能：校验原采购单已实际收货，锁定采购明细后按 received_quantity 计算可退，写入草稿。
        参数：采购单、退货仓、结算类型、原因、明细（申请退货数量和申请退款金额）。
        返回：DRAFT 采购退货单。
        异常：未收货、超量退货、超量退款、跨租户。
        核心流程：
        1. 锁 PurchaseOrder。
        2. 按 sku_id 稳定顺序锁相关 PurchaseOrderItem。
        3. 查询有效采购退货已占用数量和金额（草稿不计入）。
        4. 可退 = received_quantity - occupied。
        5. 同一事务写 PurchaseReturn + PurchaseReturnItem，flush 后生成 PRT 单号。
        为什么草稿不占用：草稿可随意改；真正业务占用从 submit 开始。
        并发：两个管理员同时创建 80/80 草稿都成功；同时提交时后一个会看到占用后失败。
        """
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_CREATE,))
        settlement = self._normalize_settlement(payload.settlement_type)
        try:
            order = self.orders.get_for_update(payload.purchase_order_id)
            if order is None:
                raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
            self._require_eligible(order.status)
            supplier = self.suppliers.get_in_tenant(order.supplier_id)
            if supplier is None:
                raise AppError("供应商不存在或不可访问", code=40460, status_code=404)
            warehouse_id = payload.warehouse_id or order.warehouse_id
            self._require_active_warehouse(warehouse_id)
            built, total_refund = self._build_items(
                order.id,
                payload.items,
                exclude_return_id=None,
            )
            record = PurchaseReturn(
                tenant_id=self.context.tenant_id,
                supplier_id=order.supplier_id,
                purchase_order_id=order.id,
                warehouse_id=warehouse_id,
                status=PurchaseReturnStatus.DRAFT.value,
                settlement_type=settlement,
                reason=payload.reason,
                description=payload.description,
                requested_refund_amount=total_refund,
                refund_status=PurchaseReturnRefundStatus.NONE.value,
                created_by=self.context.user_id,
            )
            self.returns.add(record)
            self.session.flush()
            record.purchase_return_no = f"PRT{datetime.now().year}{record.id:06d}"
            for item in built:
                item.purchase_return_id = record.id
                self.returns.add_item(item)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.returns.get_in_tenant(record.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40500, status_code=404)
        return self._out(created)

    def update_purchase_return(
        self, return_id: int, payload: PurchaseReturnUpdate
    ) -> PurchaseReturnOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_UPDATE,))
        try:
            record = self.returns.get_for_update(return_id)
            if record is None:
                raise AppError(_UNAVAILABLE, code=40500, status_code=404)
            if record.status not in EDITABLE_STATUSES:
                raise AppError(
                    "只有草稿可以修改",
                    code=40362,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_NOT_EDITABLE"},
                )
            order = self.orders.get_for_update(record.purchase_order_id)
            if order is None:
                raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
            if payload.warehouse_id is not None:
                self._require_active_warehouse(payload.warehouse_id)
                record.warehouse_id = payload.warehouse_id
            if payload.settlement_type is not None:
                record.settlement_type = self._normalize_settlement(payload.settlement_type)
            if payload.reason is not None:
                record.reason = payload.reason
            if payload.description is not None:
                record.description = payload.description
            if payload.items is not None:
                built, total_refund = self._build_items(
                    order.id,
                    payload.items,
                    exclude_return_id=return_id,
                )
                self.returns.delete_items(return_id)
                self.session.flush()
                for item in built:
                    item.purchase_return_id = record.id
                    self.returns.add_item(item)
                record.requested_refund_amount = total_refund
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_return(return_id)

    def submit_purchase_return(self, return_id: int) -> PurchaseReturnOut:
        """提交审核。草稿开始占用可退数量。提交时重新校验，不能只信创建时的结果。

        核心流程：
        1. 锁 PurchaseReturn。
        2. 幂等：已经是 PENDING_APPROVAL 则拒绝，避免重复占用。
        3. 锁原采购单和采购明细（sku_id 顺序）。
        4. 重新计算 occupied，保证 existing + requested <= received。
        5. DRAFT → PENDING_APPROVAL。
        """
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_SUBMIT,))
        try:
            record = self.returns.get_for_update(return_id)
            if record is None:
                raise AppError(_UNAVAILABLE, code=40500, status_code=404)
            if record.status == PENDING_APPROVAL:
                raise AppError(
                    "采购退货已提交审核",
                    code=40354,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_ALREADY_SUBMITTED"},
                )
            if record.status not in SUBMITTABLE_STATUSES:
                require_transition(record.status, PENDING_APPROVAL)
            require_transition(record.status, PENDING_APPROVAL)
            order = self.orders.get_for_update(record.purchase_order_id)
            if order is None:
                raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
            self._require_eligible(order.status)
            self._require_active_warehouse(record.warehouse_id)
            items = self.returns.list_items(return_id)
            if not items:
                raise AppError("提交前至少需要一条退货明细", code=40363, status_code=400)
            payload_items = [
                PurchaseReturnItemIn(
                    purchase_order_item_id=row.purchase_order_item_id,
                    purchase_receipt_item_id=row.purchase_receipt_item_id,
                    requested_return_quantity=row.requested_return_quantity,
                    requested_refund_amount=row.requested_refund_amount,
                    reason=row.reason,
                )
                for row in items
            ]
            self._build_items(order.id, payload_items, exclude_return_id=return_id)
            record.status = PENDING_APPROVAL
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_return(return_id)

    def approve_purchase_return(
        self, return_id: int, payload: PurchaseReturnApprove
    ) -> PurchaseReturnOut:
        """审核通过。可以下调批准数量/金额，不能超过申请；成功后进入待出库。

        批准数量占用可退额度（原来按申请数量占用，批准更小时释放差额）。
        不修改 Inventory。
        """
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_APPROVE,))
        try:
            record = self.returns.get_for_update(return_id)
            if record is None:
                raise AppError(_UNAVAILABLE, code=40500, status_code=404)
            if record.status == PurchaseReturnStatus.WAITING_OUTBOUND.value:
                raise AppError(
                    "采购退货已审核",
                    code=40354,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_ALREADY_APPROVED"},
                )
            require_transition(record.status, PurchaseReturnStatus.WAITING_OUTBOUND.value)
            order = self.orders.get_for_update(record.purchase_order_id)
            if order is None:
                raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
            items = self.returns.list_items(return_id)
            by_id = {row.id: row for row in items}
            overrides = {row.item_id: row for row in payload.items}
            total_approved_qty = 0
            total_approved_amt = _ZERO
            for item in items:
                override = overrides.get(item.id)
                approved_qty = (
                    override.approved_return_quantity
                    if override is not None
                    else item.requested_return_quantity
                )
                requested_amt = item.requested_refund_amount or _ZERO
                approved_amt = (
                    override.approved_refund_amount if override is not None else requested_amt
                )
                if approved_qty > item.requested_return_quantity:
                    raise AppError(
                        "批准退货数量不能超过申请数量",
                        code=40364,
                        status_code=400,
                        data={"error": "APPROVED_RETURN_EXCEEDS_REQUESTED"},
                    )
                if approved_amt > requested_amt:
                    raise AppError(
                        "批准退款金额不能超过申请金额",
                        code=40364,
                        status_code=400,
                        data={"error": "APPROVED_REFUND_EXCEEDS_REQUESTED"},
                    )
                if record.settlement_type == PurchaseReturnSettlementType.NO_REFUND.value:
                    approved_amt = _ZERO
                item.approved_return_quantity = approved_qty
                item.approved_refund_amount = approved_amt
                total_approved_qty += approved_qty
                total_approved_amt += approved_amt
            if total_approved_qty <= 0:
                raise AppError(
                    "审核至少需要批准一件退货",
                    code=40364,
                    status_code=400,
                    data={"error": "APPROVED_RETURN_EMPTY"},
                )
            if payload.items and any(row.item_id not in by_id for row in payload.items):
                raise AppError("审核明细不属于该采购退货单", code=40500, status_code=400)
            record.approved_refund_amount = total_approved_amt
            record.approved_by = self.context.user_id
            record.approved_at = datetime.now()
            record.status = PurchaseReturnStatus.WAITING_OUTBOUND.value
            if record.settlement_type == PurchaseReturnSettlementType.NO_REFUND.value:
                record.refund_status = PurchaseReturnRefundStatus.NONE.value
                record.approved_refund_amount = _ZERO
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_return(return_id)

    def reject_purchase_return(
        self, return_id: int, payload: PurchaseReturnReject
    ) -> PurchaseReturnOut:
        """拒绝采购退货，释放对可退数量的占用。"""
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_REJECT,))
        try:
            record = self.returns.get_for_update(return_id)
            if record is None:
                raise AppError(_UNAVAILABLE, code=40500, status_code=404)
            require_transition(record.status, PurchaseReturnStatus.REJECTED.value)
            record.status = PurchaseReturnStatus.REJECTED.value
            record.rejected_by = self.context.user_id
            record.rejected_at = datetime.now()
            record.reject_reason = payload.reason
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_return(return_id)

    def cancel_purchase_return(self, return_id: int) -> PurchaseReturnOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_CANCEL,))
        try:
            record = self.returns.get_for_update(return_id)
            if record is None:
                raise AppError(_UNAVAILABLE, code=40500, status_code=404)
            if record.status not in CANCELLABLE_STATUSES:
                require_transition(record.status, PurchaseReturnStatus.CANCELLED.value)
            require_transition(record.status, PurchaseReturnStatus.CANCELLED.value)
            record.status = PurchaseReturnStatus.CANCELLED.value
            record.cancelled_by = self.context.user_id
            record.cancelled_at = datetime.now()
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_return(return_id)

    def _build_items(
        self,
        purchase_order_id: int,
        payload_items: list[PurchaseReturnItemIn],
        *,
        exclude_return_id: int | None,
    ) -> tuple[list[PurchaseReturnItem], Decimal]:
        item_ids = [row.purchase_order_item_id for row in payload_items]
        locked = self.orders.lock_items_by_ids(item_ids)
        by_id = {row.id: row for row in locked}
        if len(by_id) != len(set(item_ids)):
            raise AppError("采购明细不存在或不属于本订单", code=40470, status_code=404)
        for po_item in locked:
            if po_item.purchase_order_id != purchase_order_id:
                raise AppError("采购明细不属于该采购单", code=40470, status_code=404)
        occupied_qty = self.returns.occupied_return_qty(
            item_ids,
            exclude_return_id=exclude_return_id,
        )
        occupied_amt = self.returns.occupied_refund_amount(
            item_ids,
            exclude_return_id=exclude_return_id,
        )
        built: list[PurchaseReturnItem] = []
        total_refund = _ZERO
        for row in payload_items:
            po_item = by_id[row.purchase_order_item_id]
            self._validate_item_request(
                po_item,
                row.requested_return_quantity,
                row.requested_refund_amount,
                occupied_qty.get(po_item.id, 0),
                occupied_amt.get(po_item.id, _ZERO),
            )
            amount = row.requested_refund_amount or _ZERO
            total_refund += amount
            built.append(
                PurchaseReturnItem(
                    tenant_id=self.context.tenant_id,
                    purchase_order_item_id=po_item.id,
                    purchase_receipt_item_id=row.purchase_receipt_item_id,
                    sku_id=po_item.sku_id,
                    original_received_quantity=po_item.received_quantity,
                    requested_return_quantity=row.requested_return_quantity,
                    requested_refund_amount=amount,
                    reason=row.reason,
                )
            )
        return built, total_refund

    def _validate_item_request(
        self,
        po_item: PurchaseOrderItem,
        requested_qty: int,
        requested_amt: Decimal | None,
        occupied_qty: int,
        occupied_amt: Decimal,
    ) -> None:
        if po_item.received_quantity <= 0:
            raise AppError(
                "未实际收货入库的采购明细不能退货",
                code=40350,
                status_code=400,
                data={
                    "error": "PURCHASE_RETURN_NOT_RECEIVED",
                    "purchase_order_item_id": po_item.id,
                },
            )
        returnable = po_item.received_quantity - occupied_qty
        if requested_qty > returnable:
            raise AppError(
                f"可退数量 {returnable}，申请 {requested_qty}，不能超过已收货减去有效退货占用",
                code=40351,
                status_code=400,
                data={
                    "error": "PURCHASE_RETURN_EXCEEDS_RETURNABLE",
                    "purchase_order_item_id": po_item.id,
                    "received_quantity": po_item.received_quantity,
                    "occupied_return_quantity": occupied_qty,
                    "returnable_quantity": returnable,
                    "requested_return_quantity": requested_qty,
                },
            )
        amount = requested_amt or _ZERO
        cap = self._line_refund_cap(po_item)
        leftover = cap - occupied_amt
        if leftover < 0:
            leftover = _ZERO
        if amount > leftover:
            raise AppError(
                "申请退款金额超过可退上限",
                code=40352,
                status_code=400,
                data={
                    "error": "PURCHASE_RETURN_REFUND_EXCEEDS",
                    "purchase_order_item_id": po_item.id,
                },
            )

    def _line_refund_cap(self, po_item: PurchaseOrderItem) -> Decimal:
        if po_item.unit_price is None:
            return Decimal("9999999999.99")
        return (po_item.unit_price * po_item.received_quantity).quantize(Decimal("0.01"))

    def _require_eligible(self, status: str) -> None:
        if status not in _ELIGIBLE:
            raise AppError(
                "尚未实际收货的采购单不能创建采购退货",
                code=40350,
                status_code=400,
                data={"error": "PURCHASE_RETURN_ORDER_NOT_ELIGIBLE"},
            )

    def _require_active_warehouse(self, warehouse_id: int) -> None:
        warehouse = self.warehouses.get_in_tenant(warehouse_id)
        if warehouse is None:
            raise AppError("仓库不存在或不可访问", code=40440, status_code=404)
        if warehouse.status != WarehouseStatus.ACTIVE.value:
            raise AppError(
                "只能使用启用中的仓库",
                code=40367,
                status_code=400,
                data={"error": "WAREHOUSE_NOT_ACTIVE"},
            )

    def _normalize_settlement(self, value: str) -> str:
        text = value.strip().upper()
        if text not in _SETTLEMENT:
            raise AppError(
                "结算类型必须是 REFUND 或 NO_REFUND",
                code=40353,
                status_code=400,
                data={"error": "INVALID_SETTLEMENT_TYPE"},
            )
        return text

    def _out(self, order: PurchaseReturn) -> PurchaseReturnOut:
        items = self.returns.list_items(order.id)
        stocks = {
            row.sku_id: row
            for row in self.inventories.list_by_warehouse_skus(
                order.warehouse_id,
                [row.sku_id for row in items],
            )
        }
        item_outs = [self._item_out(row, stocks.get(row.sku_id)) for row in items]
        outbounds = [
            PurchaseReturnOutboundBriefOut(
                id=row.id,
                outbound_no=row.outbound_no or "",
                warehouse_id=row.warehouse_id,
                status=row.status,
                remark=row.remark,
                confirmed_at=row.confirmed_at,
                confirmed_by=row.confirmed_by,
                created_at=row.created_at,
                items=[
                    PurchaseReturnOutboundItemOut(
                        id=line.id,
                        purchase_return_item_id=line.purchase_return_item_id,
                        sku_id=line.sku_id,
                        sku_code=(line.sku.sku_code or "") if line.sku is not None else "",
                        quantity=line.quantity,
                    )
                    for line in row.items
                ],
            )
            for row in self.outbounds.list_by_return(order.id)
        ]
        refunds = [
            SupplierRefundBriefOut(
                id=row.id,
                refund_no=row.refund_no or "",
                amount=float(row.amount),
                status=row.status,
                external_reference_no=row.external_reference_no,
                failure_reason=row.failure_reason,
                received_at=row.received_at,
                created_at=row.created_at,
            )
            for row in self.refunds.list_by_return(order.id)
        ]
        approved_qty = None
        if any(row.approved_return_quantity is not None for row in items):
            approved_qty = sum(row.approved_return_quantity or 0 for row in items)
        po = order.purchase_order
        return PurchaseReturnOut(
            id=order.id,
            purchase_return_no=order.purchase_return_no or "",
            purchase_order_id=order.purchase_order_id,
            purchase_order_no=(po.order_no or "") if po is not None else "",
            supplier_id=order.supplier_id,
            supplier_name=order.supplier.name if order.supplier is not None else "",
            warehouse_id=order.warehouse_id,
            warehouse_name=order.warehouse.name if order.warehouse is not None else "",
            status=order.status,
            settlement_type=order.settlement_type,
            reason=order.reason,
            description=order.description,
            requested_refund_amount=float(order.requested_refund_amount),
            approved_refund_amount=_money(order.approved_refund_amount),
            refund_status=order.refund_status,
            sku_count=len(items),
            requested_return_quantity=sum(row.requested_return_quantity for row in items),
            approved_return_quantity=approved_qty,
            returned_quantity=sum(row.returned_quantity for row in items),
            created_by=order.created_by,
            created_by_name=self._user_name(order.created_by),
            approved_by=order.approved_by,
            approved_by_name=self._user_name(order.approved_by),
            approved_at=order.approved_at,
            rejected_by=order.rejected_by,
            rejected_at=order.rejected_at,
            reject_reason=order.reject_reason,
            outbound_at=order.outbound_at,
            outbound_by=order.outbound_by,
            completed_at=order.completed_at,
            cancelled_at=order.cancelled_at,
            cancelled_by=order.cancelled_by,
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=item_outs,
            outbounds=outbounds,
            refunds=refunds,
        )

    def _item_out(self, item: PurchaseReturnItem, inventory=None) -> PurchaseReturnItemOut:
        sku = item.sku
        product = sku.product if sku is not None else None
        spec = sku.spec_values if sku is not None and sku.spec_values else {}
        po_item = item.purchase_order_item
        approved = item.approved_return_quantity
        requested = item.requested_return_quantity
        base_qty = approved if approved is not None else requested
        remaining = max(base_qty - item.returned_quantity, 0)
        qty = inventory.quantity if inventory is not None else 0
        reserved = inventory.reserved_quantity if inventory is not None else 0
        return PurchaseReturnItemOut(
            id=item.id,
            purchase_order_item_id=item.purchase_order_item_id,
            purchase_receipt_item_id=item.purchase_receipt_item_id,
            sku_id=item.sku_id,
            sku_code=(sku.sku_code or "") if sku is not None else "",
            sku_name=sku.name if sku is not None else "",
            product_name=product.name if product is not None else "",
            spec_values=spec if isinstance(spec, dict) else {},
            original_ordered_quantity=po_item.quantity if po_item is not None else 0,
            original_received_quantity=item.original_received_quantity,
            requested_return_quantity=item.requested_return_quantity,
            approved_return_quantity=item.approved_return_quantity,
            returned_quantity=item.returned_quantity,
            remaining_return_quantity=remaining,
            inventory_quantity=qty,
            inventory_reserved=reserved,
            inventory_available=max(qty - reserved, 0),
            requested_refund_amount=_money(item.requested_refund_amount),
            approved_refund_amount=_money(item.approved_refund_amount),
            unit_price=_money(po_item.unit_price) if po_item is not None else None,
            reason=item.reason,
        )

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.session.scalar(select(User.display_name).where(User.id == user_id))
