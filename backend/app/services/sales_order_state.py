"""销售订单状态机。状态只能通过提交 / 确认 / 取消 / 出库 / 发货 / 签收改变。"""

from app.core.exceptions import AppError
from app.models.sales_order import SalesOrderItem, SalesOrderStatus

DRAFT = SalesOrderStatus.DRAFT.value
"""草稿。可改单；可提交或取消。未预占库存。"""

PENDING_CONFIRMATION = SalesOrderStatus.PENDING_CONFIRMATION.value
"""待确认。提交后的审核态。确认才预占；取消不动库存。"""

WAITING_OUTBOUND = SalesOrderStatus.WAITING_OUTBOUND.value
"""待出库。已确认并预占。尚未正式出库时取消必须释放预占。"""

PARTIALLY_OUTBOUND = SalesOrderStatus.PARTIALLY_OUTBOUND.value
"""部分出库。已经有正式出库，不能整单取消。"""

OUTBOUNDED = SalesOrderStatus.OUTBOUNDED.value
"""已出库。购买数量都已离开库存账面。"""

PARTIALLY_SHIPPED = SalesOrderStatus.PARTIALLY_SHIPPED.value
"""部分发货。已经有物流单确认交给承运商。"""

SHIPPED = SalesOrderStatus.SHIPPED.value
"""已发货。订单数量都已交给承运商，尚未全部签收。"""

COMPLETED = SalesOrderStatus.COMPLETED.value
"""已完成。全部物流单都已签收。"""

CANCELLED = SalesOrderStatus.CANCELLED.value
"""已取消。终态，不能再变。"""

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({PENDING_CONFIRMATION, CANCELLED}),
    PENDING_CONFIRMATION: frozenset({WAITING_OUTBOUND, CANCELLED}),
    WAITING_OUTBOUND: frozenset({PARTIALLY_OUTBOUND, OUTBOUNDED, CANCELLED}),
    PARTIALLY_OUTBOUND: frozenset({OUTBOUNDED, PARTIALLY_SHIPPED, SHIPPED}),
    OUTBOUNDED: frozenset({PARTIALLY_SHIPPED, SHIPPED}),
    PARTIALLY_SHIPPED: frozenset({SHIPPED, COMPLETED}),
    SHIPPED: frozenset({COMPLETED}),
    COMPLETED: frozenset(),
    CANCELLED: frozenset(),
}

EDITABLE_STATUSES = frozenset({DRAFT})
SUBMITTABLE_STATUSES = frozenset({DRAFT})
CANCELLABLE_STATUSES = frozenset({DRAFT, PENDING_CONFIRMATION, WAITING_OUTBOUND})
OUTBOUNDABLE_STATUSES = frozenset({WAITING_OUTBOUND, PARTIALLY_OUTBOUND, PARTIALLY_SHIPPED})


def can_transition(current: str, target: str) -> bool:
    allowed = ALLOWED_TRANSITIONS.get(current)
    return allowed is not None and target in allowed


def require_transition(current: str, target: str) -> None:
    """非法流转必须拒绝。前端藏按钮只是体验，服务端才是规则。"""
    if not can_transition(current, target):
        raise AppError(
            f"当前状态不能从 {current} 变更为 {target}",
            code=40114,
            status_code=400,
            data={"error": "INVALID_SALES_ORDER_TRANSITION", "from": current, "to": target},
        )


def require_editable(status: str) -> None:
    """非草稿禁止改核心字段。"""
    if status not in EDITABLE_STATUSES:
        raise AppError(
            "只有草稿可以修改客户、仓库、收货信息和明细",
            code=40112,
            status_code=400,
            data={"error": "SALES_ORDER_NOT_EDITABLE"},
        )


def status_from_quantities(
    items: list[SalesOrderItem],
    *,
    all_delivered: bool = False,
) -> str:
    """根据明细数量计算订单履约状态。

    为什么不用前端 PATCH status：COMPLETED 必须由签收结果决定。
    all_delivered 只在全部物流单都已签收时为真。
    """
    if not items:
        return WAITING_OUTBOUND
    all_outbound = all(item.outbound_quantity == item.quantity for item in items)
    some_outbound = any(item.outbound_quantity > 0 for item in items)
    all_shipped = all(item.shipped_quantity == item.quantity for item in items)
    some_shipped = any(item.shipped_quantity > 0 for item in items)
    if all_shipped and all_delivered:
        return COMPLETED
    if all_shipped:
        return SHIPPED
    if some_shipped:
        return PARTIALLY_SHIPPED
    if all_outbound:
        return OUTBOUNDED
    if some_outbound:
        return PARTIALLY_OUTBOUND
    return WAITING_OUTBOUND


def apply_fulfillment_status(
    order_status: str,
    items: list[SalesOrderItem],
    *,
    all_delivered: bool = False,
) -> str:
    """算出目标状态；没有变化就返回当前状态，避免无意义流转。"""
    target = status_from_quantities(items, all_delivered=all_delivered)
    if target == order_status:
        return order_status
    require_transition(order_status, target)
    return target
