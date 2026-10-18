"""销售售后。创建只占用可退额度，不改库存、不改原销售明细数量。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.events import AggregateType, EventType
from app.core.exceptions import AppError
from app.core.identity_names import identity_display_name
from app.core.operations import OperationAction, OperationModule
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.after_sale import (
    AfterSaleItem,
    AfterSaleOrder,
    AfterSaleStatus,
    AfterSaleType,
    RefundStatus,
)
from app.models.return_order import ReturnCondition, ReturnOrder, ReturnOrderItem, ReturnOrderStatus
from app.models.sales_order import SalesOrderItem, SalesOrderStatus
from app.models.warehouse import WarehouseStatus
from app.repositories.after_sale import AfterSaleRepository
from app.repositories.customer import CustomerRepository
from app.repositories.return_order import ReturnOrderRepository
from app.repositories.sales_order import SalesOrderRepository
from app.repositories.warehouse import WarehouseRepository
from app.schemas.after_sale import (
    AfterSaleApprove,
    AfterSaleCreate,
    AfterSaleItemOut,
    AfterSaleListItem,
    AfterSaleListOut,
    AfterSaleOut,
    AfterSalePreviewItem,
    AfterSalePreviewOut,
    AfterSaleReject,
)
from app.services.authorization import AuthorizationService
from app.services.observability import emit_event, emit_operation

_UNAVAILABLE = "售后单不存在或不可访问"
_ELIGIBLE = {
    SalesOrderStatus.PARTIALLY_OUTBOUND.value,
    SalesOrderStatus.OUTBOUNDED.value,
    SalesOrderStatus.PARTIALLY_SHIPPED.value,
    SalesOrderStatus.SHIPPED.value,
    SalesOrderStatus.COMPLETED.value,
}
_ZERO = Decimal("0")


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


class AfterSaleService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.after_sales = AfterSaleRepository(session, context.tenant_id)
        self.returns = ReturnOrderRepository(session, context.tenant_id)
        self.orders = SalesOrderRepository(session, context.tenant_id)
        self.customers = CustomerRepository(session, context.tenant_id)
        self.warehouses = WarehouseRepository(session, context.tenant_id)

    def preview(self, sales_order_id: int) -> AfterSalePreviewOut:
        """创建售后前的可退数量 / 可退金额预览。"""
        self.auth.require_all(self.context, (PermissionCode.AFTER_SALE_READ,))
        order = self.orders.get_in_tenant(sales_order_id)
        if order is None:
            raise AppError("销售订单不存在或不可访问", code=40480, status_code=404)
        items = self.orders.list_items(sales_order_id)
        occupied_qty = self.after_sales.occupied_return_qty([row.id for row in items])
        occupied_amt = self.after_sales.occupied_refund_amount([row.id for row in items])
        preview_items: list[AfterSalePreviewItem] = []
        for row in items:
            occ_qty = occupied_qty.get(row.id, 0)
            occ_amt = occupied_amt.get(row.id, _ZERO)
            returnable = max(row.outbound_quantity - occ_qty, 0)
            line_cap = self._line_refund_cap(row)
            refundable = line_cap - occ_amt
            if refundable < 0:
                refundable = _ZERO
            sku = row.sku
            product = sku.product if sku is not None else None
            spec = sku.spec_values if sku is not None and sku.spec_values else {}
            preview_items.append(
                AfterSalePreviewItem(
                    sales_order_item_id=row.id,
                    sku_id=row.sku_id,
                    sku_code=(sku.sku_code or "") if sku is not None else "",
                    sku_name=sku.name if sku is not None else "",
                    product_name=product.name if product is not None else "",
                    spec_values=spec if isinstance(spec, dict) else {},
                    original_quantity=row.quantity,
                    outbound_quantity=row.outbound_quantity,
                    occupied_return_quantity=occ_qty,
                    returnable_quantity=returnable,
                    unit_price=_money(row.unit_price),
                    occupied_refund_amount=float(occ_amt),
                    refundable_amount=float(refundable),
                )
            )
        total = None
        if any(row.unit_price is not None for row in items):
            total = float(
                sum((row.unit_price or _ZERO) * row.quantity for row in items)
            )
        return AfterSalePreviewOut(
            sales_order_id=order.id,
            sales_order_no=order.order_no or "",
            customer_id=order.customer_id,
            customer_name=order.customer.name if order.customer is not None else "",
            warehouse_id=order.warehouse_id,
            warehouse_name=order.warehouse.name if order.warehouse is not None else "",
            status=order.status,
            currency_code=order.currency_code,
            total_amount=total,
            eligible=order.status in _ELIGIBLE,
            items=preview_items,
        )

    def list_after_sales(
        self,
        *,
        q: str | None,
        sales_order_id: int | None,
        customer_id: int | None,
        sku_code: str | None,
        after_sale_type: str | None,
        status: str | None,
        refund_status: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        page: int,
        page_size: int,
    ) -> AfterSaleListOut:
        self.auth.require_all(self.context, (PermissionCode.AFTER_SALE_READ,))
        rows, total = self.after_sales.list_page(
            q=q,
            sales_order_id=sales_order_id,
            customer_id=customer_id,
            sku_code=sku_code,
            after_sale_type=after_sale_type,
            status=status,
            refund_status=refund_status,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
        items = [
            AfterSaleListItem(
                id=order.id,
                after_sale_no=order.after_sale_no or "",
                sales_order_id=order.sales_order_id,
                sales_order_no=order_no or "",
                customer_id=order.customer_id,
                customer_name=customer_name or "",
                type=order.type,
                status=order.status,
                refund_status=order.refund_status,
                return_quantity=int(return_qty or 0),
                requested_refund_amount=float(order.requested_refund_amount),
                approved_refund_amount=_money(order.approved_refund_amount),
                requested_by_name=requested_name,
                created_at=order.created_at,
            )
            for order, order_no, customer_name, requested_name, return_qty in rows
        ]
        return AfterSaleListOut(items=items, total=total, page=page, page_size=page_size)

    def get_after_sale(self, after_sale_id: int) -> AfterSaleOut:
        self.auth.require_all(self.context, (PermissionCode.AFTER_SALE_READ,))
        order = self.after_sales.get_in_tenant(after_sale_id)
        if order is None:
            raise AppError(_UNAVAILABLE, code=40494, status_code=404)
        return self._out(order)

    def create_after_sale(self, payload: AfterSaleCreate) -> AfterSaleOut:
        """创建售后申请。只占用可退额度，不改库存、不改 SalesOrderItem.quantity。

        功能：校验已履约订单，锁定销售明细后按出库数量计算可退，写入售后单。
        参数：销售订单、售后类型、原因、明细（退货数量和申请退款金额）。
        返回：PENDING_APPROVAL 的售后单。
        异常：未出库订单、超量退货、超量退款、跨租户。
        核心流程：
        1. 锁 SalesOrder。
        2. 按 sku_id 稳定顺序锁相关 SalesOrderItem。
        3. 查询有效售后已占用数量和金额。
        4. 可退 = outbound_quantity - occupied。
        5. 同一事务写 AfterSaleOrder + AfterSaleItem。
        为什么 PENDING 也占用：否则两个请求可以同时各退 8，订单只有 10。
        """
        self.auth.require_all(self.context, (PermissionCode.AFTER_SALE_CREATE,))
        sale_type = self._normalize_type(payload.type)
        try:
            order = self.orders.get_for_update(payload.sales_order_id)
            if order is None:
                raise AppError("销售订单不存在或不可访问", code=40480, status_code=404)
            if order.status not in _ELIGIBLE:
                raise AppError(
                    "尚未正式出库的订单不能申请售后，请取消订单释放预占",
                    code=40301,
                    status_code=400,
                    data={"error": "AFTER_SALE_ORDER_NOT_ELIGIBLE"},
                )
            customer = self.customers.get_in_tenant(order.customer_id)
            if customer is None:
                raise AppError("客户不存在或不可访问", code=40470, status_code=404)
            item_ids = [row.sales_order_item_id for row in payload.items]
            # 统一按 sku_id 排序加锁，降低多个售后事务互相等待形成死锁的概率。
            locked = self.orders.lock_items_by_ids(item_ids)
            by_id = {row.id: row for row in locked}
            if len(by_id) != len(set(item_ids)):
                raise AppError("销售明细不存在或不属于本订单", code=40480, status_code=404)
            for so_item in locked:
                if so_item.sales_order_id != order.id:
                    raise AppError("销售明细不属于该订单", code=40480, status_code=404)
            occupied_qty = self.after_sales.occupied_return_qty(item_ids)
            occupied_amt = self.after_sales.occupied_refund_amount(item_ids)
            built: list[AfterSaleItem] = []
            total_refund = _ZERO
            total_return = 0
            for row in payload.items:
                so_item = by_id[row.sales_order_item_id]
                self._validate_item_request(
                    sale_type,
                    so_item,
                    row.return_quantity,
                    row.requested_refund_amount,
                    occupied_qty.get(so_item.id, 0),
                    occupied_amt.get(so_item.id, _ZERO),
                )
                total_refund += row.requested_refund_amount
                total_return += row.return_quantity
                built.append(
                    AfterSaleItem(
                        tenant_id=self.context.tenant_id,
                        sales_order_item_id=so_item.id,
                        sku_id=so_item.sku_id,
                        original_quantity=so_item.quantity,
                        return_quantity=row.return_quantity,
                        requested_refund_amount=row.requested_refund_amount,
                        reason=row.reason,
                    )
                )
            self._validate_type_totals(sale_type, total_return, total_refund)
            after_sale = AfterSaleOrder(
                tenant_id=self.context.tenant_id,
                sales_order_id=order.id,
                customer_id=order.customer_id,
                type=sale_type,
                status=AfterSaleStatus.PENDING_APPROVAL.value,
                reason=payload.reason or "",
                description=payload.description,
                currency_code=order.currency_code,
                requested_refund_amount=total_refund,
                refund_status=RefundStatus.NONE.value,
                requested_by=self.context.user_id,
            )
            self.after_sales.add(after_sale)
            self.session.flush()
            after_sale.after_sale_no = f"AS{datetime.now().year}{after_sale.id:06d}"
            for item in built:
                item.after_sale_order_id = after_sale.id
                self.after_sales.add_item(item)
            emit_event(
                self.session,
                self.context,
                event_type=EventType.AFTER_SALE_CREATED,
                aggregate_type=AggregateType.AFTER_SALE,
                aggregate_id=after_sale.id,
                reference_type="SALES_ORDER",
                reference_id=order.id,
                payload={"after_sale_no": after_sale.after_sale_no, "type": after_sale.type},
            )
            emit_operation(
                self.session,
                self.context,
                action=OperationAction.CREATE.value,
                module=OperationModule.AFTER_SALE.value,
                resource_type="AFTER_SALE",
                resource_id=after_sale.id,
                resource_name=after_sale.after_sale_no,
                description="创建售后申请",
            )
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        created = self.after_sales.get_in_tenant(after_sale.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40494, status_code=404)
        return self._out(created)

    def approve_after_sale(self, after_sale_id: int, payload: AfterSaleApprove) -> AfterSaleOut:
        """审核通过。批准数量/金额不能大于申请；需要退货时同一事务创建退货单。"""
        self.auth.require_all(self.context, (PermissionCode.AFTER_SALE_APPROVE,))
        try:
            order = self.after_sales.get_for_update(after_sale_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40494, status_code=404)
            if order.status == AfterSaleStatus.WAITING_RETURN.value:
                raise AppError(
                    "售后单已经审核通过",
                    code=40305,
                    status_code=400,
                    data={"error": "AFTER_SALE_ALREADY_APPROVED"},
                )
            if order.status == AfterSaleStatus.WAITING_REFUND.value:
                raise AppError(
                    "售后单已经审核通过",
                    code=40305,
                    status_code=400,
                    data={"error": "AFTER_SALE_ALREADY_APPROVED"},
                )
            if order.status == AfterSaleStatus.COMPLETED.value:
                raise AppError(
                    "售后单已经审核通过",
                    code=40305,
                    status_code=400,
                    data={"error": "AFTER_SALE_ALREADY_APPROVED"},
                )
            if order.status != AfterSaleStatus.PENDING_APPROVAL.value:
                raise AppError(
                    "只有待审核的售后单可以批准",
                    code=40300,
                    status_code=400,
                    data={"error": "INVALID_AFTER_SALE_STATUS"},
                )
            items = self.after_sales.list_items(after_sale_id)
            approve_map = {row.item_id: row for row in payload.items}
            total_approved_refund = _ZERO
            total_approved_return = 0
            for item in items:
                patch = approve_map.get(item.id)
                approved_return = (
                    patch.approved_return_quantity if patch is not None else item.return_quantity
                )
                approved_refund = (
                    patch.approved_refund_amount
                    if patch is not None
                    else item.requested_refund_amount
                )
                if approved_return > item.return_quantity:
                    raise AppError(
                        "批准退货数量不能大于申请数量",
                        code=40308,
                        status_code=400,
                        data={"error": "AFTER_SALE_APPROVED_EXCEEDS_REQUESTED"},
                    )
                if approved_refund > item.requested_refund_amount:
                    raise AppError(
                        "批准退款金额不能大于申请金额",
                        code=40308,
                        status_code=400,
                        data={"error": "AFTER_SALE_APPROVED_EXCEEDS_REQUESTED"},
                    )
                item.approved_return_quantity = approved_return
                item.approved_refund_amount = approved_refund
                total_approved_return += approved_return
                total_approved_refund += approved_refund
            self._validate_type_totals(order.type, total_approved_return, total_approved_refund)
            order.approved_refund_amount = total_approved_refund
            order.approved_by = self.context.user_id
            order.approved_at = datetime.now()
            if order.type == AfterSaleType.REFUND_ONLY.value:
                order.status = AfterSaleStatus.WAITING_REFUND.value
                order.refund_status = RefundStatus.PENDING.value
            else:
                warehouse_id = payload.warehouse_id
                if warehouse_id is None:
                    sales = self.orders.get_in_tenant(order.sales_order_id)
                    warehouse_id = sales.warehouse_id if sales is not None else None
                if warehouse_id is None:
                    raise AppError("退货仓库不存在或不可访问", code=40440, status_code=404)
                self._require_active_warehouse(warehouse_id)
                self._create_return_order(order, items, warehouse_id)
                order.status = AfterSaleStatus.WAITING_RETURN.value
                order.refund_status = RefundStatus.NONE.value
            emit_event(
                self.session,
                self.context,
                event_type=EventType.AFTER_SALE_APPROVED,
                aggregate_type=AggregateType.AFTER_SALE,
                aggregate_id=order.id,
                reference_type="SALES_ORDER",
                reference_id=order.sales_order_id,
                payload={"after_sale_no": order.after_sale_no, "type": order.type},
            )
            emit_operation(
                self.session,
                self.context,
                action=OperationAction.APPROVE.value,
                module=OperationModule.AFTER_SALE.value,
                resource_type="AFTER_SALE",
                resource_id=order.id,
                resource_name=order.after_sale_no,
                description="审核通过售后申请",
            )
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_after_sale(after_sale_id)

    def reject_after_sale(self, after_sale_id: int, payload: AfterSaleReject) -> AfterSaleOut:
        """拒绝售后。REJECTED 不再占用可退数量，需要重新申请请建新单。"""
        self.auth.require_all(self.context, (PermissionCode.AFTER_SALE_REJECT,))
        try:
            order = self.after_sales.get_for_update(after_sale_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40494, status_code=404)
            if order.status == AfterSaleStatus.REJECTED.value:
                raise AppError(
                    "售后单已经拒绝",
                    code=40306,
                    status_code=400,
                    data={"error": "AFTER_SALE_ALREADY_REJECTED"},
                )
            if order.status != AfterSaleStatus.PENDING_APPROVAL.value:
                raise AppError(
                    "只有待审核的售后单可以拒绝",
                    code=40300,
                    status_code=400,
                    data={"error": "INVALID_AFTER_SALE_STATUS"},
                )
            order.status = AfterSaleStatus.REJECTED.value
            order.rejected_by = self.context.user_id
            order.rejected_at = datetime.now()
            order.reject_reason = payload.reason
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_after_sale(after_sale_id)

    def cancel_after_sale(self, after_sale_id: int) -> AfterSaleOut:
        self.auth.require_all(self.context, (PermissionCode.AFTER_SALE_CANCEL,))
        try:
            order = self.after_sales.get_for_update(after_sale_id)
            if order is None:
                raise AppError(_UNAVAILABLE, code=40494, status_code=404)
            if order.status == AfterSaleStatus.CANCELLED.value:
                raise AppError(
                    "售后单已经取消",
                    code=40307,
                    status_code=400,
                    data={"error": "AFTER_SALE_CANNOT_CANCEL"},
                )
            if order.status != AfterSaleStatus.PENDING_APPROVAL.value:
                raise AppError(
                    "只有待审核的售后单可以取消",
                    code=40307,
                    status_code=400,
                    data={"error": "AFTER_SALE_CANNOT_CANCEL"},
                )
            order.status = AfterSaleStatus.CANCELLED.value
            order.cancelled_at = datetime.now()
            order.cancelled_by = self.context.user_id
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return self.get_after_sale(after_sale_id)

    def _create_return_order(
        self,
        after_sale: AfterSaleOrder,
        items: list[AfterSaleItem],
        warehouse_id: int,
    ) -> ReturnOrder:
        returning = [
            item
            for item in items
            if (item.approved_return_quantity or 0) > 0
        ]
        if not returning:
            raise AppError(
                "退货类型售后必须批准至少一个退货数量",
                code=40310,
                status_code=400,
                data={"error": "AFTER_SALE_RETURN_QTY_REQUIRED"},
            )
        order = ReturnOrder(
            tenant_id=self.context.tenant_id,
            after_sale_order_id=after_sale.id,
            sales_order_id=after_sale.sales_order_id,
            warehouse_id=warehouse_id,
            status=ReturnOrderStatus.WAITING_RETURN.value,
        )
        self.returns.add(order)
        self.session.flush()
        order.return_no = f"RT{datetime.now().year}{order.id:06d}"
        for item in returning:
            self.returns.add_item(
                ReturnOrderItem(
                    tenant_id=self.context.tenant_id,
                    return_order_id=order.id,
                    after_sale_item_id=item.id,
                    sales_order_item_id=item.sales_order_item_id,
                    sku_id=item.sku_id,
                    expected_quantity=item.approved_return_quantity or 0,
                    received_quantity=0,
                    inbound_quantity=0,
                    condition=ReturnCondition.GOOD.value,
                )
            )
        return order

    def _validate_item_request(
        self,
        sale_type: str,
        so_item: SalesOrderItem,
        return_qty: int,
        refund_amount: Decimal,
        occupied_qty: int,
        occupied_amt: Decimal,
    ) -> None:
        returnable = so_item.outbound_quantity - occupied_qty
        if return_qty > returnable:
            raise AppError(
                f"可退数量 {max(returnable, 0)}，申请退货 {return_qty}",
                code=40302,
                status_code=400,
                data={
                    "error": "AFTER_SALE_EXCEEDS_RETURNABLE",
                    "sales_order_item_id": so_item.id,
                    "returnable_quantity": max(returnable, 0),
                    "requested_quantity": return_qty,
                },
            )
        line_cap = self._line_refund_cap(so_item)
        refundable = line_cap - occupied_amt
        if refund_amount > refundable:
            raise AppError(
                "申请退款金额超过可退金额",
                code=40303,
                status_code=400,
                data={
                    "error": "AFTER_SALE_EXCEEDS_REFUNDABLE",
                    "sales_order_item_id": so_item.id,
                    "refundable_amount": float(max(refundable, _ZERO)),
                },
            )

    @staticmethod
    def _validate_type_totals(sale_type: str, return_qty: int, refund_amount: Decimal) -> None:
        if sale_type == AfterSaleType.REFUND_ONLY.value:
            if return_qty > 0:
                raise AppError(
                    "仅退款不能填写退货数量",
                    code=40310,
                    status_code=400,
                    data={"error": "AFTER_SALE_RETURN_QTY_REQUIRED"},
                )
            if refund_amount <= 0:
                raise AppError(
                    "仅退款必须填写退款金额",
                    code=40311,
                    status_code=400,
                    data={"error": "AFTER_SALE_REFUND_REQUIRED"},
                )
            return
        if return_qty <= 0:
            raise AppError(
                "退货类型售后必须填写退货数量",
                code=40310,
                status_code=400,
                data={"error": "AFTER_SALE_RETURN_QTY_REQUIRED"},
            )
        if sale_type == AfterSaleType.RETURN_AND_REFUND.value and refund_amount <= 0:
            raise AppError(
                "退货退款必须填写退款金额",
                code=40311,
                status_code=400,
                data={"error": "AFTER_SALE_REFUND_REQUIRED"},
            )
        if sale_type == AfterSaleType.RETURN_ONLY.value and refund_amount > 0:
            raise AppError(
                "仅退货不能申请退款",
                code=40312,
                status_code=400,
                data={"error": "AFTER_SALE_REFUND_NOT_ALLOWED"},
            )

    @staticmethod
    def _line_refund_cap(so_item: SalesOrderItem) -> Decimal:
        price = so_item.unit_price or _ZERO
        return price * so_item.outbound_quantity

    @staticmethod
    def _normalize_type(value: str) -> str:
        if value not in {item.value for item in AfterSaleType}:
            raise AppError(
                "售后类型不合法",
                code=40304,
                status_code=400,
                data={"error": "AFTER_SALE_TYPE_INVALID"},
            )
        return value

    def _require_active_warehouse(self, warehouse_id: int) -> None:
        warehouse = self.warehouses.get_in_tenant(warehouse_id)
        if warehouse is None:
            raise AppError("仓库不存在或不可访问", code=40440, status_code=404)
        if warehouse.status != WarehouseStatus.ACTIVE.value:
            raise AppError("只能退回到启用中的仓库", code=40097, status_code=400)

    def _user_name(self, user_id: int | None) -> str | None:
        return identity_display_name(self.session, user_id)

    def _out(self, order: AfterSaleOrder) -> AfterSaleOut:
        items = sorted(order.items, key=lambda row: (row.sku_id, row.id))
        sales = order.sales_order
        customer = order.customer
        return_order = self.returns.get_by_after_sale(order.id)
        return AfterSaleOut(
            id=order.id,
            after_sale_no=order.after_sale_no or "",
            sales_order_id=order.sales_order_id,
            sales_order_no=sales.order_no if sales is not None and sales.order_no else "",
            customer_id=order.customer_id,
            customer_name=customer.name if customer is not None else "",
            type=order.type,
            status=order.status,
            reason=order.reason,
            description=order.description,
            currency_code=order.currency_code,
            requested_refund_amount=float(order.requested_refund_amount),
            approved_refund_amount=_money(order.approved_refund_amount),
            refund_status=order.refund_status,
            return_quantity=sum(row.return_quantity for row in items),
            requested_by=order.requested_by,
            requested_by_name=self._user_name(order.requested_by),
            approved_by=order.approved_by,
            approved_by_name=self._user_name(order.approved_by),
            approved_at=order.approved_at,
            rejected_by=order.rejected_by,
            rejected_at=order.rejected_at,
            reject_reason=order.reject_reason,
            completed_at=order.completed_at,
            cancelled_at=order.cancelled_at,
            cancelled_by=order.cancelled_by,
            created_at=order.created_at,
            updated_at=order.updated_at,
            return_order_id=return_order.id if return_order is not None else None,
            items=[self._item_out(row) for row in items],
        )

    @staticmethod
    def _item_out(item: AfterSaleItem) -> AfterSaleItemOut:
        sku = item.sku
        product = sku.product if sku is not None else None
        spec = sku.spec_values if sku is not None and sku.spec_values else {}
        so_item = item.sales_order_item
        return AfterSaleItemOut(
            id=item.id,
            sales_order_item_id=item.sales_order_item_id,
            sku_id=item.sku_id,
            sku_code=(sku.sku_code or "") if sku is not None else "",
            sku_name=sku.name if sku is not None else "",
            product_name=product.name if product is not None else "",
            spec_values=spec if isinstance(spec, dict) else {},
            original_quantity=item.original_quantity,
            outbound_quantity=so_item.outbound_quantity if so_item is not None else 0,
            return_quantity=item.return_quantity,
            approved_return_quantity=item.approved_return_quantity,
            requested_refund_amount=float(item.requested_refund_amount),
            approved_refund_amount=_money(item.approved_refund_amount),
            reason=item.reason,
        )
