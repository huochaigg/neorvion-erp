"""采购退货出库。确认时扣减 available inventory，不改 reserved。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import AggregateType, EventType
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.inventory import InventoryTransactionType
from app.models.purchase_return import (
    PURCHASE_RETURN_REFERENCE,
    PurchaseReturn,
    PurchaseReturnRefundStatus,
    PurchaseReturnSettlementType,
    PurchaseReturnStatus,
)
from app.models.purchase_return_outbound import (
    PurchaseReturnOutbound,
    PurchaseReturnOutboundItem,
    PurchaseReturnOutboundStatus,
)
from app.models.user import User
from app.repositories.inventory import InventoryRepository
from app.repositories.purchase_return import PurchaseReturnRepository
from app.repositories.purchase_return_outbound import PurchaseReturnOutboundRepository
from app.schemas.purchase_return_outbound import (
    PurchaseReturnOutboundCreate,
    PurchaseReturnOutboundItemOut,
    PurchaseReturnOutboundListItem,
    PurchaseReturnOutboundListOut,
    PurchaseReturnOutboundOut,
)
from app.services.authorization import AuthorizationService
from app.services.inventory import InventoryService
from app.services.observability import emit_event
from app.services.purchase_return_state import OUTBOUND_STATUSES, require_transition

_UNAVAILABLE = "采购退货出库单不存在或不可访问"


class PurchaseReturnOutboundService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.outbounds = PurchaseReturnOutboundRepository(session, context.tenant_id)
        self.returns = PurchaseReturnRepository(session, context.tenant_id)
        self.inventories = InventoryRepository(session, context.tenant_id)
        self.inventory = InventoryService(session, context)

    def list_outbounds(
        self,
        *,
        q: str | None,
        purchase_return_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> PurchaseReturnOutboundListOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_READ,))
        rows, total = self.outbounds.list_page(
            q=q,
            purchase_return_id=purchase_return_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            PurchaseReturnOutboundListItem(
                id=row.id,
                outbound_no=row.outbound_no or "",
                purchase_return_id=row.purchase_return_id,
                purchase_return_no=return_no or "",
                purchase_order_no=order_no or "",
                supplier_name=supplier_name or "",
                warehouse_name=warehouse_name or "",
                status=row.status,
                total_quantity=int(total_qty or 0),
                confirmed_at=row.confirmed_at,
                created_at=row.created_at,
            )
            for row, return_no, order_no, supplier_name, warehouse_name, total_qty in rows
        ]
        return PurchaseReturnOutboundListOut(
            items=items, total=total, page=page, page_size=page_size
        )

    def get_outbound(self, outbound_id: int) -> PurchaseReturnOutboundOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_READ,))
        outbound = self.outbounds.get_in_tenant(outbound_id)
        if outbound is None:
            raise AppError(_UNAVAILABLE, code=40501, status_code=404)
        return self._out(outbound)

    def create_outbound(
        self, return_id: int, payload: PurchaseReturnOutboundCreate
    ) -> PurchaseReturnOutboundOut:
        """创建退货出库草稿。不修改库存。"""
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_OUTBOUND,))
        try:
            record = self.returns.get_for_update(return_id)
            if record is None:
                raise AppError("采购退货单不存在或不可访问", code=40500, status_code=404)
            if record.status not in OUTBOUND_STATUSES:
                raise AppError(
                    "当前状态不能创建退货出库单",
                    code=40366,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_NOT_WAITING_OUTBOUND"},
                )
            return_items = {row.id: row for row in self.returns.list_items(return_id)}
            built: list[PurchaseReturnOutboundItem] = []
            for row in payload.items:
                item = return_items.get(row.purchase_return_item_id)
                if item is None:
                    raise AppError(
                        "退货明细不存在或不属于该采购退货单",
                        code=40500,
                        status_code=400,
                    )
                approved = item.approved_return_quantity or 0
                remaining = approved - item.returned_quantity
                if row.quantity > remaining:
                    raise AppError(
                        f"剩余待退 {remaining}，本次不能出库 {row.quantity}",
                        code=40356,
                        status_code=400,
                        data={
                            "error": "PURCHASE_RETURN_OUTBOUND_EXCEEDS_REMAINING",
                            "purchase_return_item_id": item.id,
                            "remaining_return_quantity": remaining,
                            "requested_quantity": row.quantity,
                        },
                    )
                built.append(
                    PurchaseReturnOutboundItem(
                        tenant_id=self.context.tenant_id,
                        purchase_return_item_id=item.id,
                        sku_id=item.sku_id,
                        quantity=row.quantity,
                    )
                )
            outbound = PurchaseReturnOutbound(
                tenant_id=self.context.tenant_id,
                purchase_return_id=return_id,
                warehouse_id=record.warehouse_id,
                status=PurchaseReturnOutboundStatus.DRAFT.value,
                remark=payload.remark,
                created_by=self.context.user_id,
            )
            self.outbounds.add(outbound)
            self.session.flush()
            outbound.outbound_no = f"PRO{datetime.now().year}{outbound.id:06d}"
            for item in built:
                item.purchase_return_outbound_id = outbound.id
                self.outbounds.add_item(item)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.outbounds.get_in_tenant(outbound.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40501, status_code=404)
        return self._out(created)

    def confirm_purchase_return_outbound(self, outbound_id: int) -> PurchaseReturnOutboundOut:
        """确认采购退货出库。真正减少库存 quantity，reserved 不变。

        功能：把出库草稿变成已确认，按 available 扣减仓库库存并写流水。
        参数：出库单 id。
        返回：CONFIRMED 出库单。
        异常：状态不对、可用不足、超过剩余待退。任一 SKU 失败整单 rollback。
        核心流程：
        1. 锁 PurchaseReturnOutbound。
        2. 已 CONFIRMED 则拒绝，避免重复扣库存。
        3. 锁 PurchaseReturn，校验 WAITING_OUTBOUND / PARTIALLY_RETURNED。
        4. 取出明细，按 sku_id / id 稳定排序后扣减。
        5. 复用 InventoryService.deduct_available_within_transaction。
        6. 写 PURCHASE_RETURN_OUTBOUND 流水，reference_type=PURCHASE_RETURN。
        7. 更新 PurchaseReturnItem.returned_quantity 与退货单状态。
        8. 全部批准数量已出库：NO_REFUND → COMPLETED；REFUND → WAITING_REFUND。
        为什么不能动 reserved：预占代表已经承诺给客户，采购退货不能偷偷释放销售订单。
        """
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_OUTBOUND,))
        try:
            outbound = self.outbounds.get_for_update(outbound_id)
            if outbound is None:
                raise AppError(_UNAVAILABLE, code=40501, status_code=404)
            if outbound.status == PurchaseReturnOutboundStatus.CONFIRMED.value:
                raise AppError(
                    "退货出库已经确认，不能重复扣库存",
                    code=40355,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_OUTBOUND_ALREADY_CONFIRMED"},
                )
            if outbound.status != PurchaseReturnOutboundStatus.DRAFT.value:
                raise AppError(
                    "只有草稿出库单可以确认",
                    code=40365,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_OUTBOUND_NOT_DRAFT"},
                )
            record = self.returns.get_for_update(outbound.purchase_return_id)
            if record is None:
                raise AppError("采购退货单不存在或不可访问", code=40500, status_code=404)
            if record.status not in OUTBOUND_STATUSES:
                raise AppError(
                    "当前采购退货状态不能确认出库",
                    code=40366,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_NOT_WAITING_OUTBOUND"},
                )
            lines = self.outbounds.list_items(outbound_id)
            if not lines:
                raise AppError("出库单没有明细", code=40363, status_code=400)
            return_items = {row.id: row for row in self.returns.list_items(record.id)}
            # 多 SKU 按 sku_id 再按明细 id 排序加锁/扣减，降低与销售出库、调拨死锁概率。
            ordered = sorted(lines, key=lambda row: (row.sku_id, row.id))
            for line in ordered:
                item = return_items.get(line.purchase_return_item_id)
                if item is None:
                    raise AppError("退货明细不存在", code=40500, status_code=400)
                approved = item.approved_return_quantity or 0
                remaining = approved - item.returned_quantity
                if line.quantity > remaining:
                    raise AppError(
                        f"剩余待退 {remaining}，本次不能出库 {line.quantity}",
                        code=40356,
                        status_code=400,
                        data={"error": "PURCHASE_RETURN_OUTBOUND_EXCEEDS_REMAINING"},
                    )
                sku = line.sku
                self.inventory.deduct_available_within_transaction(
                    warehouse_id=outbound.warehouse_id,
                    sku_id=line.sku_id,
                    quantity=line.quantity,
                    sku_code=(sku.sku_code if sku is not None else None),
                    reference_type=PURCHASE_RETURN_REFERENCE,
                    reference_id=record.id,
                    remark=f"采购退货出库 {outbound.outbound_no}",
                    tx_type=InventoryTransactionType.PURCHASE_RETURN_OUTBOUND.value,
                )
                item.returned_quantity += line.quantity
            outbound.status = PurchaseReturnOutboundStatus.CONFIRMED.value
            outbound.confirmed_at = datetime.now()
            outbound.confirmed_by = self.context.user_id
            record.outbound_at = outbound.confirmed_at
            record.outbound_by = self.context.user_id
            self._advance_after_outbound(record)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_outbound(outbound_id)

    def cancel_outbound(self, outbound_id: int) -> PurchaseReturnOutboundOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RETURN_OUTBOUND,))
        try:
            outbound = self.outbounds.get_for_update(outbound_id)
            if outbound is None:
                raise AppError(_UNAVAILABLE, code=40501, status_code=404)
            if outbound.status == PurchaseReturnOutboundStatus.CANCELLED.value:
                raise AppError(
                    "出库单已取消",
                    code=40365,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_OUTBOUND_ALREADY_CANCELLED"},
                )
            if outbound.status != PurchaseReturnOutboundStatus.DRAFT.value:
                raise AppError(
                    "已确认的退货出库不能取消",
                    code=40365,
                    status_code=400,
                    data={"error": "PURCHASE_RETURN_OUTBOUND_NOT_DRAFT"},
                )
            outbound.status = PurchaseReturnOutboundStatus.CANCELLED.value
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_outbound(outbound_id)

    def _advance_after_outbound(self, record: PurchaseReturn) -> None:
        items = self.returns.list_items(record.id)
        all_out = all(
            (item.approved_return_quantity or 0) <= item.returned_quantity for item in items
        )
        any_out = any(item.returned_quantity > 0 for item in items)
        if all_out:
            if record.settlement_type == PurchaseReturnSettlementType.NO_REFUND.value:
                require_transition(record.status, PurchaseReturnStatus.COMPLETED.value)
                record.status = PurchaseReturnStatus.COMPLETED.value
                record.completed_at = datetime.now()
                record.refund_status = PurchaseReturnRefundStatus.NONE.value
                emit_event(
                    self.session,
                    self.context,
                    event_type=EventType.PURCHASE_RETURN_COMPLETED,
                    aggregate_type=AggregateType.PURCHASE_RETURN,
                    aggregate_id=record.id,
                    payload={"purchase_return_no": record.purchase_return_no},
                )
                return
            require_transition(record.status, PurchaseReturnStatus.WAITING_REFUND.value)
            record.status = PurchaseReturnStatus.WAITING_REFUND.value
            record.refund_status = PurchaseReturnRefundStatus.PENDING.value
            approved = record.approved_refund_amount or record.requested_refund_amount
            if approved is not None and approved <= 0:
                record.status = PurchaseReturnStatus.COMPLETED.value
                record.completed_at = datetime.now()
                record.refund_status = PurchaseReturnRefundStatus.NONE.value
                emit_event(
                    self.session,
                    self.context,
                    event_type=EventType.PURCHASE_RETURN_COMPLETED,
                    aggregate_type=AggregateType.PURCHASE_RETURN,
                    aggregate_id=record.id,
                    payload={"purchase_return_no": record.purchase_return_no},
                )
            return
        if any_out and record.status == PurchaseReturnStatus.WAITING_OUTBOUND.value:
            require_transition(record.status, PurchaseReturnStatus.PARTIALLY_RETURNED.value)
            record.status = PurchaseReturnStatus.PARTIALLY_RETURNED.value

    def _out(self, outbound: PurchaseReturnOutbound) -> PurchaseReturnOutboundOut:
        parent = outbound.purchase_return
        po = parent.purchase_order if parent is not None else None
        supplier = parent.supplier if parent is not None else None
        lines = self.outbounds.list_items(outbound.id)
        stocks = {
            row.sku_id: row
            for row in self.inventories.list_by_warehouse_skus(
                outbound.warehouse_id,
                [line.sku_id for line in lines],
            )
        }
        item_outs: list[PurchaseReturnOutboundItemOut] = []
        for line in lines:
            sku = line.sku
            product = sku.product if sku is not None else None
            spec = sku.spec_values if sku is not None and sku.spec_values else {}
            parent_item = line.purchase_return_item
            approved = parent_item.approved_return_quantity if parent_item is not None else 0
            returned = parent_item.returned_quantity if parent_item is not None else 0
            stock = stocks.get(line.sku_id)
            available = 0
            if stock is not None:
                available = max(stock.quantity - stock.reserved_quantity, 0)
            item_outs.append(
                PurchaseReturnOutboundItemOut(
                    id=line.id,
                    purchase_return_item_id=line.purchase_return_item_id,
                    sku_id=line.sku_id,
                    sku_code=(sku.sku_code or "") if sku is not None else "",
                    sku_name=sku.name if sku is not None else "",
                    product_name=product.name if product is not None else "",
                    spec_values=spec if isinstance(spec, dict) else {},
                    quantity=line.quantity,
                    approved_return_quantity=approved or 0,
                    already_returned_quantity=returned,
                    remaining_return_quantity=max((approved or 0) - returned, 0),
                    inventory_available=available,
                )
            )
        return PurchaseReturnOutboundOut(
            id=outbound.id,
            outbound_no=outbound.outbound_no or "",
            purchase_return_id=outbound.purchase_return_id,
            purchase_return_no=parent.purchase_return_no if parent is not None else "",
            purchase_order_id=parent.purchase_order_id if parent is not None else 0,
            purchase_order_no=po.order_no if po is not None else "",
            supplier_id=parent.supplier_id if parent is not None else 0,
            supplier_name=supplier.name if supplier is not None else "",
            warehouse_id=outbound.warehouse_id,
            warehouse_name=outbound.warehouse.name if outbound.warehouse is not None else "",
            status=outbound.status,
            remark=outbound.remark,
            confirmed_at=outbound.confirmed_at,
            confirmed_by=outbound.confirmed_by,
            confirmed_by_name=self._user_name(outbound.confirmed_by),
            created_by=outbound.created_by,
            created_by_name=self._user_name(outbound.created_by),
            created_at=outbound.created_at,
            updated_at=outbound.updated_at,
            items=item_outs,
        )

    def _user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.session.scalar(select(User.display_name).where(User.id == user_id))
