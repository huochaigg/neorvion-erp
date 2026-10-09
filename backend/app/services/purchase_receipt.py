"""采购收货。草稿不入库；确认收货才增加 quantity，并且和采购进度同一事务。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.product import ProductSku
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.purchase_receipt import (
    PURCHASE_RECEIPT_REFERENCE,
    PurchaseReceipt,
    PurchaseReceiptItem,
    PurchaseReceiptStatus,
)
from app.models.user import User
from app.repositories.purchase import PurchaseOrderRepository
from app.repositories.purchase_receipt import PurchaseReceiptRepository
from app.schemas.purchase_receipt import (
    PurchaseReceiptCreate,
    PurchaseReceiptItemIn,
    PurchaseReceiptItemOut,
    PurchaseReceiptListItem,
    PurchaseReceiptListOut,
    PurchaseReceiptOut,
    PurchaseReceiptUpdate,
)
from app.services.authorization import AuthorizationService
from app.services.inventory import InventoryService
from app.services.purchase_state import (
    PARTIALLY_RECEIVED,
    RECEIVABLE_STATUSES,
    RECEIVED,
    WAITING_RECEIPT,
    require_transition,
)

_UNAVAILABLE = "采购收货单不存在或不可访问"
_DRAFT = PurchaseReceiptStatus.DRAFT.value
_CONFIRMED = PurchaseReceiptStatus.CONFIRMED.value
_CANCELLED = PurchaseReceiptStatus.CANCELLED.value


class PurchaseReceiptService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.receipts = PurchaseReceiptRepository(session, context.tenant_id)
        self.orders = PurchaseOrderRepository(session, context.tenant_id)
        self.inventory = InventoryService(session, context)

    def list_receipts(
        self,
        *,
        q: str | None,
        purchase_order_id: int | None,
        supplier_id: int | None,
        warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> PurchaseReceiptListOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RECEIPT_READ,))
        rows, total = self.receipts.list_page(
            q=q,
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            PurchaseReceiptListItem(
                id=receipt.id,
                receipt_no=receipt.receipt_no or "",
                purchase_order_id=receipt.purchase_order_id,
                purchase_order_no=order_no or "",
                supplier_name=supplier_name,
                warehouse_id=receipt.warehouse_id,
                warehouse_name=warehouse_name,
                status=receipt.status,
                sku_count=int(sku_count),
                total_received=int(total_received),
                received_by_name=receiver_name,
                received_at=receipt.received_at,
                created_at=receipt.created_at,
            )
            for (
                receipt,
                order_no,
                supplier_name,
                warehouse_name,
                receiver_name,
                sku_count,
                total_received,
            ) in rows
        ]
        return PurchaseReceiptListOut(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_receipt(self, receipt_id: int) -> PurchaseReceiptOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RECEIPT_READ,))
        receipt = self.receipts.get_in_tenant(receipt_id)
        if receipt is None:
            raise AppError(_UNAVAILABLE, code=40480, status_code=404)
        return self._out(receipt)

    def create_receipt(self, payload: PurchaseReceiptCreate) -> PurchaseReceiptOut:
        """创建草稿收货单。不改库存，也不增加采购明细的已收数量。"""
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RECEIPT_CREATE,))
        try:
            order = self.orders.get_for_update(payload.purchase_order_id)
            if order is None:
                raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
            lines = self._plan_lines(order, payload.items)
            receipt = PurchaseReceipt(
                tenant_id=self.context.tenant_id,
                purchase_order_id=order.id,
                warehouse_id=order.warehouse_id,
                status=_DRAFT,
                remark=payload.remark,
                created_by=self.context.user_id,
            )
            self.receipts.add(receipt)
            self.session.flush()
            receipt.receipt_no = f"PR{datetime.now().year}{receipt.id:06d}"
            self._insert_items(receipt.id, lines)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.receipts.get_in_tenant(receipt.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40480, status_code=404)
        return self._out(created)

    def update_receipt(self, receipt_id: int, payload: PurchaseReceiptUpdate) -> PurchaseReceiptOut:
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RECEIPT_UPDATE,))
        try:
            receipt = self.receipts.get_for_update(receipt_id)
            if receipt is None:
                raise AppError(_UNAVAILABLE, code=40480, status_code=404)
            if receipt.status != _DRAFT:
                raise AppError(
                    "只有草稿收货单可以修改数量",
                    code=40133,
                    status_code=400,
                    data={"error": "PURCHASE_RECEIPT_NOT_EDITABLE"},
                )
            order = self.orders.get_for_update(receipt.purchase_order_id)
            if order is None:
                raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
            lines = self._plan_lines(order, payload.items)
            self.receipts.delete_items(receipt.id)
            self.session.flush()
            receipt.remark = payload.remark
            self._insert_items(receipt.id, lines)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.receipts.get_in_tenant(receipt_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40480, status_code=404)
        return self._out(updated)

    def confirm_receipt(self, receipt_id: int) -> PurchaseReceiptOut:
        """确认收货，并在同一事务里增加库存。

        功能：草稿收货单变成已确认，采购已收数量增加，库存 quantity 增加。
        参数：收货单 id。调用方需要 purchase:receipt:confirm。
        返回：已确认的收货单。
        异常：
        - 已经确认：拒绝，不再次入库
        - 已作废、采购单不可收、本次数量超过剩余
        - 任一 SKU 入库失败则整单回滚
        核心流程：
        1. SELECT FOR UPDATE 锁收货单，避免同一张单确认两次。
        2. 锁采购单和采购明细。明细按 sku_id 升序，和库存加锁顺序一致。
        3. 用锁定后的已收数量再判断本次是否超额。
        4. 按 sku_id 调用 InventoryService.inbound_within_transaction。
           它只加 quantity，不改 reserved，并且不自己 commit。
        5. 回写采购已收、采购单状态、收货单已确认。
        6. 一次 commit。

        为什么确认才入库：草稿只是仓库准备记录到货。没确认之前货还不能算进账面。
        为什么 reserved 不变：入库的是新到的货，不是已经被销售订单占住的货。
        """
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RECEIPT_CONFIRM,))
        try:
            receipt = self.receipts.get_for_update(receipt_id)
            if receipt is None:
                raise AppError(_UNAVAILABLE, code=40480, status_code=404)
            if receipt.status == _CONFIRMED:
                raise AppError(
                    "收货单已经确认，不能重复入库",
                    code=40131,
                    status_code=400,
                    data={"error": "PURCHASE_RECEIPT_ALREADY_CONFIRMED"},
                )
            if receipt.status != _DRAFT:
                raise AppError(
                    "只有草稿收货单可以确认",
                    code=40130,
                    status_code=400,
                    data={"error": "INVALID_PURCHASE_RECEIPT_STATUS"},
                )
            order = self.orders.get_for_update(receipt.purchase_order_id)
            if order is None:
                raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
            if order.status not in RECEIVABLE_STATUSES:
                raise AppError(
                    "采购单当前不能收货",
                    code=40136,
                    status_code=400,
                    data={"error": "PURCHASE_ORDER_NOT_RECEIVABLE"},
                )
            po_items = {row.id: row for row in self.receipts.list_po_items_for_update(order.id)}
            draft_items = self.receipts.get_in_tenant(receipt.id)
            if draft_items is None or not draft_items.items:
                raise AppError("收货单没有明细", code=40134, status_code=400)
            # 先抄成普通数据。入库里的条件 UPDATE 会 expire_all，不能靠未提交的 ORM 改动。
            plan = sorted(
                [
                    (item.sku_id, item.purchase_order_item_id, item.received_quantity)
                    for item in draft_items.items
                ],
                key=lambda row: row[0],
            )
            receipt_no = receipt.receipt_no or str(receipt.id)
            warehouse_id = receipt.warehouse_id
            for sku_id, po_item_id, qty in plan:
                po_item = po_items.get(po_item_id)
                if po_item is None:
                    raise AppError("采购明细不存在", code=40470, status_code=404)
                remaining = po_item.quantity - po_item.received_quantity
                if qty > remaining:
                    raise AppError(
                        "本次收货超过采购剩余数量",
                        code=40132,
                        status_code=400,
                        data={
                            "error": "PURCHASE_RECEIPT_EXCEEDS_REMAINING",
                            "sku_id": sku_id,
                            "requested_quantity": qty,
                            "remaining_quantity": remaining,
                        },
                    )
            for sku_id, _po_item_id, qty in plan:
                self.inventory.inbound_within_transaction(
                    warehouse_id=warehouse_id,
                    sku_id=sku_id,
                    quantity=qty,
                    reference_type=PURCHASE_RECEIPT_REFERENCE,
                    reference_id=receipt_id,
                    remark=f"采购收货 {receipt_no} 入库",
                )
            locked = self.receipts.get_for_update(receipt_id)
            if locked is None or locked.status != _DRAFT:
                raise AppError(
                    "收货单状态已被其他人修改，请刷新后重试",
                    code=40131,
                    status_code=400,
                    data={"error": "PURCHASE_RECEIPT_ALREADY_CONFIRMED"},
                )
            fresh_items = {row.id: row for row in self.receipts.list_po_items_for_update(order.id)}
            for _sku_id, po_item_id, qty in plan:
                po_item = fresh_items[po_item_id]
                if po_item.received_quantity + qty > po_item.quantity:
                    raise AppError(
                        "本次收货超过采购剩余数量",
                        code=40132,
                        status_code=400,
                        data={"error": "PURCHASE_RECEIPT_EXCEEDS_REMAINING"},
                    )
                po_item.received_quantity += qty
            locked.status = _CONFIRMED
            locked.received_at = datetime.now()
            locked.received_by = self.context.user_id
            fresh_order = self.orders.get_for_update(order.id)
            if fresh_order is None:
                raise AppError("采购单不存在或不可访问", code=40470, status_code=404)
            self._sync_purchase_status(fresh_order, list(fresh_items.values()))
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.receipts.get_in_tenant(receipt_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40480, status_code=404)
        return self._out(updated)

    def cancel_receipt(self, receipt_id: int) -> PurchaseReceiptOut:
        """作废草稿。已确认的收货已经入库，不能在这里撤销。"""
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_RECEIPT_CANCEL,))
        try:
            receipt = self.receipts.get_for_update(receipt_id)
            if receipt is None:
                raise AppError(_UNAVAILABLE, code=40480, status_code=404)
            if receipt.status == _CANCELLED:
                raise AppError(
                    "收货单已经作废",
                    code=40135,
                    status_code=400,
                    data={"error": "PURCHASE_RECEIPT_ALREADY_CANCELLED"},
                )
            if receipt.status != _DRAFT:
                raise AppError(
                    "已确认的收货单不能取消",
                    code=40130,
                    status_code=400,
                    data={"error": "INVALID_PURCHASE_RECEIPT_STATUS"},
                )
            receipt.status = _CANCELLED
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        updated = self.receipts.get_in_tenant(receipt_id)
        if updated is None:
            raise AppError(_UNAVAILABLE, code=40480, status_code=404)
        return self._out(updated)

    def _plan_lines(
        self,
        order: PurchaseOrder,
        items: list[PurchaseReceiptItemIn],
    ) -> list[tuple[PurchaseOrderItem, int]]:
        if order.status not in RECEIVABLE_STATUSES:
            raise AppError(
                "只有待收货或部分收货的采购单可以创建收货单",
                code=40136,
                status_code=400,
                data={"error": "PURCHASE_ORDER_NOT_RECEIVABLE"},
            )
        by_id = {item.id: item for item in order.items}
        seen: set[int] = set()
        lines: list[tuple[PurchaseOrderItem, int]] = []
        for incoming in items:
            if incoming.purchase_order_item_id in seen:
                raise AppError(
                    "同一采购明细不能在一张收货单里出现两次",
                    code=40134,
                    status_code=400,
                )
            seen.add(incoming.purchase_order_item_id)
            po_item = by_id.get(incoming.purchase_order_item_id)
            if po_item is None:
                raise AppError("采购明细不存在", code=40470, status_code=404)
            remaining = po_item.quantity - po_item.received_quantity
            if incoming.received_quantity > remaining:
                raise AppError(
                    "本次收货超过剩余待收数量",
                    code=40132,
                    status_code=400,
                    data={
                        "error": "PURCHASE_RECEIPT_EXCEEDS_REMAINING",
                        "sku_id": po_item.sku_id,
                        "requested_quantity": incoming.received_quantity,
                        "remaining_quantity": remaining,
                    },
                )
            lines.append((po_item, incoming.received_quantity))
        return lines

    def _insert_items(
        self,
        receipt_id: int,
        lines: list[tuple[PurchaseOrderItem, int]],
    ) -> None:
        for po_item, qty in lines:
            remaining = po_item.quantity - po_item.received_quantity
            self.session.add(
                PurchaseReceiptItem(
                    tenant_id=self.context.tenant_id,
                    purchase_receipt_id=receipt_id,
                    purchase_order_item_id=po_item.id,
                    sku_id=po_item.sku_id,
                    expected_quantity=remaining,
                    received_quantity=qty,
                )
            )

    def _sync_purchase_status(self, order: PurchaseOrder, items: list[PurchaseOrderItem]) -> None:
        if items and all(item.received_quantity == item.quantity for item in items):
            target = RECEIVED
        elif any(item.received_quantity > 0 for item in items):
            target = PARTIALLY_RECEIVED
        else:
            target = WAITING_RECEIPT
        if order.status != target:
            require_transition(order.status, target)
            order.status = target

    def _out(self, receipt: PurchaseReceipt) -> PurchaseReceiptOut:
        order = receipt.purchase_order
        supplier_name = order.supplier.name if order is not None and order.supplier else ""
        warehouse_name = ""
        if order is not None and order.warehouse is not None:
            warehouse_name = order.warehouse.name
        receiver = self.session.get(User, receipt.received_by) if receipt.received_by else None
        items = [self._item_out(item) for item in receipt.items]
        return PurchaseReceiptOut(
            id=receipt.id,
            receipt_no=receipt.receipt_no or "",
            purchase_order_id=receipt.purchase_order_id,
            purchase_order_no=order.order_no if order is not None and order.order_no else "",
            supplier_name=supplier_name,
            warehouse_id=receipt.warehouse_id,
            warehouse_name=warehouse_name,
            status=receipt.status,
            remark=receipt.remark,
            received_by=receipt.received_by,
            received_by_name=None if receiver is None else receiver.display_name,
            received_at=receipt.received_at,
            created_by=receipt.created_by,
            created_at=receipt.created_at,
            sku_count=len(items),
            total_received=sum(item.received_quantity for item in items),
            items=items,
        )

    @staticmethod
    def _item_out(item: PurchaseReceiptItem) -> PurchaseReceiptItemOut:
        sku: ProductSku | None = item.sku
        po_item = item.purchase_order_item
        cumulative = 0 if po_item is None else po_item.received_quantity
        before = cumulative
        receipt = item.receipt
        if receipt is not None and receipt.status == _CONFIRMED:
            before = cumulative - item.received_quantity
        return PurchaseReceiptItemOut(
            id=item.id,
            purchase_order_item_id=item.purchase_order_item_id,
            sku_id=item.sku_id,
            sku_code="" if sku is None or sku.sku_code is None else sku.sku_code,
            sku_name="" if sku is None else sku.name,
            product_name="" if sku is None or sku.product is None else sku.product.name,
            order_quantity=0 if po_item is None else po_item.quantity,
            received_before=before,
            expected_quantity=item.expected_quantity,
            received_quantity=item.received_quantity,
        )
