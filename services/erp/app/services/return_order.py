"""销售退货收货与入库。退货入库只增加 quantity，不恢复原订单 reserved。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.events import AggregateType, EventType
from app.core.exceptions import AppError
from app.core.identity_names import identity_display_name
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.after_sale import AfterSaleStatus, AfterSaleType, RefundStatus
from app.models.inventory import InventoryTransactionType
from app.models.return_order import (
    RETURN_ORDER_REFERENCE,
    ReturnCondition,
    ReturnOrder,
    ReturnOrderItem,
    ReturnOrderStatus,
)
from app.repositories.after_sale import AfterSaleRepository
from app.repositories.return_order import ReturnOrderRepository
from app.schemas.return_order import (
    ReturnOrderItemOut,
    ReturnOrderListItem,
    ReturnOrderListOut,
    ReturnOrderOut,
    ReturnOrderUpdate,
    ReturnReceiveIn,
)
from app.services.authorization import AuthorizationService
from app.services.inventory import InventoryService
from app.services.observability import emit_event

_UNAVAILABLE = "退货单不存在或不可访问"
_EDITABLE = {
    ReturnOrderStatus.WAITING_RETURN.value,
    ReturnOrderStatus.PARTIALLY_RECEIVED.value,
    ReturnOrderStatus.RECEIVED.value,
    ReturnOrderStatus.PARTIALLY_INBOUNDED.value,
}
_CONDITIONS = {item.value for item in ReturnCondition}


class ReturnOrderService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.returns = ReturnOrderRepository(session, context.tenant_id)
        self.after_sales = AfterSaleRepository(session, context.tenant_id)
        self.inventory = InventoryService(session, context)

    def list_returns(
        self,
        *,
        q: str | None,
        after_sale_id: int | None,
        sales_order_id: int | None,
        warehouse_id: int | None,
        status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> ReturnOrderListOut:
        self.auth.require_all(self.context, (PermissionCode.RETURN_ORDER_READ,))
        rows, total = self.returns.list_page(
            q=q,
            after_sale_id=after_sale_id,
            sales_order_id=sales_order_id,
            warehouse_id=warehouse_id,
            status=status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            ReturnOrderListItem(
                id=order.id,
                return_no=order.return_no or "",
                after_sale_order_id=order.after_sale_order_id,
                after_sale_no=after_sale_no or "",
                sales_order_id=order.sales_order_id,
                sales_order_no=sales_no or "",
                customer_name=customer_name or "",
                warehouse_name=warehouse_name or "",
                status=order.status,
                expected_quantity=int(expected or 0),
                received_quantity=int(received or 0),
                inbound_quantity=int(inbound or 0),
                created_at=order.created_at,
            )
            for (
                order,
                after_sale_no,
                sales_no,
                customer_name,
                warehouse_name,
                expected,
                received,
                inbound,
            ) in rows
        ]
        return ReturnOrderListOut(items=items, total=total, page=page, page_size=page_size)

    def get_return(self, return_id: int) -> ReturnOrderOut:
        self.auth.require_all(self.context, (PermissionCode.RETURN_ORDER_READ,))
        order = self.returns.get_in_tenant(return_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40495, status_code=404)
        return self._out(order)

    def update_return(self, return_id: int, payload: ReturnOrderUpdate) -> ReturnOrderOut:
        self.auth.require_all(self.context, (PermissionCode.RETURN_ORDER_RECEIVE,))
        try:
            order = self.returns.get_for_update(return_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40495, status_code=404)
            if order.status not in _EDITABLE:
                raise AppError(
                    "当前退货单不能修改物流信息",
                    code=40320,
                    status_code=400,
                    data={"error": "INVALID_RETURN_STATUS"},
                )
            if payload.tracking_no is not None:
                order.tracking_no = payload.tracking_no
            if payload.carrier_name is not None:
                order.carrier_name = payload.carrier_name
            if payload.remark is not None:
                order.remark = payload.remark
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_return(return_id)

    def receive(self, return_id: int, payload: ReturnReceiveIn) -> ReturnOrderOut:
        """累计实收数量。可以分多次，累计不能超过预期数量。"""
        self.auth.require_all(self.context, (PermissionCode.RETURN_ORDER_RECEIVE,))
        try:
            order = self.returns.get_for_update(return_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40495, status_code=404)
            if order.status == ReturnOrderStatus.INBOUNDED.value:
                raise AppError(
                    "退货单已经入库，不能再收货",
                    code=40321,
                    status_code=400,
                    data={"error": "RETURN_ALREADY_INBOUNDED"},
                )
            if order.status not in _EDITABLE:
                raise AppError(
                    "当前退货单不能收货",
                    code=40320,
                    status_code=400,
                    data={"error": "INVALID_RETURN_STATUS"},
                )
            for row in payload.items:
                if row.condition not in _CONDITIONS:
                    raise AppError(
                        "退货商品状态不合法",
                        code=40323,
                        status_code=400,
                        data={"error": "RETURN_INVALID_CONDITION"},
                    )
                item = self.returns.get_item(return_id, row.item_id)
                if item is None:
                    raise AppError(_UNAVAILABLE, code=40495, status_code=404)
                new_received = item.received_quantity + row.received_quantity
                if new_received > item.expected_quantity:
                    raise AppError(
                        "实收数量不能超过预期退货数量",
                        code=40320,
                        status_code=400,
                        data={"error": "RETURN_RECEIVED_EXCEEDS"},
                    )
                item.received_quantity = new_received
                item.condition = row.condition
                if row.remark is not None:
                    item.remark = row.remark
            items = self.returns.list_items(return_id)
            order.status = self._receive_status(items)
            order.received_at = datetime.now()
            order.received_by = self.context.user_id
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_return(return_id)

    def confirm_inbound(self, return_id: int) -> ReturnOrderOut:
        """确认退货入库。GOOD 增加普通库存；残次品只记已收，不入普通库存。

        功能：把已收且尚未入库的 GOOD 数量加到目标仓 quantity。
        参数：退货单 id。调用方需要 return_order:inbound。
        返回：入库后的退货单。
        异常：已入库则拒绝，不再次加库存（幂等）。
        核心流程：
        1. 锁退货单。
        2. 明细按 sku_id 稳定排序。
        3. GOOD：inbound_delta = received - inbound；复用 inbound_within_transaction。
        4. DAMAGED / UNSELLABLE：inbound_quantity 保持 0。
        5. reserved 不变。退回的是已出库商品，原预占在出库时已经扣掉。
        6. 库存、流水、退货单、售后状态同一事务提交。
        """
        self.auth.require_all(self.context, (PermissionCode.RETURN_ORDER_INBOUND,))
        try:
            order = self.returns.get_for_update(return_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40495, status_code=404)
            if order.status == ReturnOrderStatus.INBOUNDED.value:
                raise AppError(
                    "退货单已经入库，不能重复增加库存",
                    code=40321,
                    status_code=400,
                    data={"error": "RETURN_ALREADY_INBOUNDED"},
                )
            items = self.returns.list_items(return_id)
            if not items:
                raise AppError("退货单没有明细", code=40320, status_code=400)
            if sum(row.received_quantity for row in items) <= 0:
                raise AppError(
                    "还没有收到退货，不能入库",
                    code=40322,
                    status_code=400,
                    data={"error": "RETURN_NOTHING_TO_INBOUND"},
                )
            # 先抄成普通数据。库存条件 UPDATE 会 expire_all。
            # 统一按 sku_id 排序后再加库存，降低死锁概率。
            plan = sorted(
                [
                    (
                        item.id,
                        item.sku_id,
                        item.received_quantity,
                        item.inbound_quantity,
                        item.condition,
                    )
                    for item in items
                ],
                key=lambda row: (row[1], row[0]),
            )
            return_no = order.return_no or str(order.id)
            warehouse_id = order.warehouse_id
            for item_id, sku_id, received, inbound_qty, condition in plan:
                delta = 0
                if condition == ReturnCondition.GOOD.value:
                    delta = received - inbound_qty
                if delta > 0:
                    self.inventory.inbound_within_transaction(
                        warehouse_id=warehouse_id,
                        sku_id=sku_id,
                        quantity=delta,
                        reference_type=RETURN_ORDER_REFERENCE,
                        reference_id=return_id,
                        remark=f"退货 {return_no} 入库",
                        tx_type=InventoryTransactionType.RETURN_INBOUND.value,
                    )
                locked_item = self.returns.get_item(return_id, item_id)
                if locked_item is None:
                    raise AppError(_UNAVAILABLE, code=40495, status_code=404)
                if condition == ReturnCondition.GOOD.value:
                    locked_item.inbound_quantity = received
            locked = self.returns.get_for_update(return_id)
            if locked is None or locked.status == ReturnOrderStatus.INBOUNDED.value:
                raise AppError(
                    "退货单状态已变化，请刷新后重试",
                    code=40320,
                    status_code=400,
                    data={"error": "INVALID_RETURN_STATUS"},
                )
            refreshed = self.returns.list_items(return_id)
            locked.status = self._inbound_status(refreshed)
            if locked.status in {
                ReturnOrderStatus.PARTIALLY_INBOUNDED.value,
                ReturnOrderStatus.INBOUNDED.value,
            }:
                locked.confirmed_at = datetime.now()
                locked.confirmed_by = self.context.user_id
            if locked.status == ReturnOrderStatus.INBOUNDED.value:
                self._complete_after_sale_if_ready(locked.after_sale_order_id)
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_return(return_id)

    def _complete_after_sale_if_ready(self, after_sale_id: int) -> None:
        after_sale = self.after_sales.get_for_update(after_sale_id)
        if after_sale is None:
            return
        if after_sale.type == AfterSaleType.RETURN_ONLY.value:
            after_sale.status = AfterSaleStatus.COMPLETED.value
            after_sale.completed_at = datetime.now()
            after_sale.refund_status = RefundStatus.NONE.value
            emit_event(
                self.session,
                self.context,
                event_type=EventType.AFTER_SALE_COMPLETED,
                aggregate_type=AggregateType.AFTER_SALE,
                aggregate_id=after_sale.id,
                reference_type="SALES_ORDER",
                reference_id=after_sale.sales_order_id,
                payload={"after_sale_no": after_sale.after_sale_no},
            )
            return
        if after_sale.type == AfterSaleType.RETURN_AND_REFUND.value:
            after_sale.status = AfterSaleStatus.WAITING_REFUND.value
            after_sale.refund_status = RefundStatus.PENDING.value

    @staticmethod
    def _receive_status(items: list[ReturnOrderItem]) -> str:
        if all(row.received_quantity >= row.expected_quantity for row in items):
            return ReturnOrderStatus.RECEIVED.value
        if any(row.received_quantity > 0 for row in items):
            return ReturnOrderStatus.PARTIALLY_RECEIVED.value
        return ReturnOrderStatus.WAITING_RETURN.value

    @staticmethod
    def _inbound_status(items: list[ReturnOrderItem]) -> str:
        fully_received = all(row.received_quantity >= row.expected_quantity for row in items)
        inbound_done = all(_item_inbound_done(row) for row in items)
        if fully_received and inbound_done:
            return ReturnOrderStatus.INBOUNDED.value
        if any(row.inbound_quantity > 0 for row in items) or (
            fully_received and inbound_done is False and any(
                row.condition != ReturnCondition.GOOD.value for row in items
            )
        ):
            if fully_received and inbound_done:
                return ReturnOrderStatus.INBOUNDED.value
            if any(row.inbound_quantity > 0 for row in items):
                return ReturnOrderStatus.PARTIALLY_INBOUNDED.value
        if fully_received:
            return ReturnOrderStatus.RECEIVED.value
        if any(row.received_quantity > 0 for row in items):
            return ReturnOrderStatus.PARTIALLY_RECEIVED.value
        return ReturnOrderStatus.WAITING_RETURN.value

    def _user_name(self, user_id: int | None) -> str | None:
        return identity_display_name(self.session, user_id)

    def _out(self, order: ReturnOrder) -> ReturnOrderOut:
        items = sorted(order.items, key=lambda row: (row.sku_id, row.id))
        after_sale = order.after_sale_order
        sales = order.sales_order
        warehouse = order.warehouse
        customer_name = ""
        if after_sale is not None and after_sale.customer is not None:
            customer_name = after_sale.customer.name
        return ReturnOrderOut(
            id=order.id,
            return_no=order.return_no or "",
            after_sale_order_id=order.after_sale_order_id,
            after_sale_no=(after_sale.after_sale_no or "") if after_sale is not None else "",
            sales_order_id=order.sales_order_id,
            sales_order_no=(sales.order_no or "") if sales is not None else "",
            customer_id=after_sale.customer_id if after_sale is not None else 0,
            customer_name=customer_name,
            warehouse_id=order.warehouse_id,
            warehouse_name=warehouse.name if warehouse is not None else "",
            status=order.status,
            tracking_no=order.tracking_no,
            carrier_name=order.carrier_name,
            remark=order.remark,
            expected_quantity=sum(row.expected_quantity for row in items),
            received_quantity=sum(row.received_quantity for row in items),
            inbound_quantity=sum(row.inbound_quantity for row in items),
            received_at=order.received_at,
            received_by=order.received_by,
            received_by_name=self._user_name(order.received_by),
            confirmed_at=order.confirmed_at,
            confirmed_by=order.confirmed_by,
            confirmed_by_name=self._user_name(order.confirmed_by),
            created_at=order.created_at,
            updated_at=order.updated_at,
            items=[_item_out(row) for row in items],
        )


def _item_inbound_done(item: ReturnOrderItem) -> bool:
    if item.condition == ReturnCondition.GOOD.value:
        return (
            item.inbound_quantity >= item.received_quantity
            and item.received_quantity >= item.expected_quantity
        )
    return item.received_quantity >= item.expected_quantity


def _item_out(item: ReturnOrderItem) -> ReturnOrderItemOut:
    sku = item.sku
    product = sku.product if sku is not None else None
    spec = sku.spec_values if sku is not None and sku.spec_values else {}
    return ReturnOrderItemOut(
        id=item.id,
        after_sale_item_id=item.after_sale_item_id,
        sales_order_item_id=item.sales_order_item_id,
        sku_id=item.sku_id,
        sku_code=(sku.sku_code or "") if sku is not None else "",
        sku_name=sku.name if sku is not None else "",
        product_name=product.name if product is not None else "",
        spec_values=spec if isinstance(spec, dict) else {},
        expected_quantity=item.expected_quantity,
        received_quantity=item.received_quantity,
        inbound_quantity=item.inbound_quantity,
        condition=item.condition,
        remark=item.remark,
    )
