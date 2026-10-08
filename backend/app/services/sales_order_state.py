"""销售订单状态机。状态只能通过提交 / 确认 / 取消改变，不能直接改 status 字段。"""

from app.core.exceptions import AppError
from app.models.sales_order import SalesOrderStatus

DRAFT = SalesOrderStatus.DRAFT.value
"""草稿。可改单；可提交或取消。未预占库存。"""

PENDING_CONFIRMATION = SalesOrderStatus.PENDING_CONFIRMATION.value
"""待确认。提交后的审核态。确认才预占；取消不动库存。"""

WAITING_OUTBOUND = SalesOrderStatus.WAITING_OUTBOUND.value
"""待出库。已确认并预占。尚未正式出库时取消必须释放预占。"""

PARTIALLY_SHIPPED = SalesOrderStatus.PARTIALLY_SHIPPED.value
"""部分出库。已经有正式出库，不能整单取消，剩余预占继续出。"""

SHIPPED = SalesOrderStatus.SHIPPED.value
"""已出库。购买数量都已发完。"""

CANCELLED = SalesOrderStatus.CANCELLED.value
"""已取消。终态，不能再变。"""

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({PENDING_CONFIRMATION, CANCELLED}),
    PENDING_CONFIRMATION: frozenset({WAITING_OUTBOUND, CANCELLED}),
    WAITING_OUTBOUND: frozenset({PARTIALLY_SHIPPED, SHIPPED, CANCELLED}),
    PARTIALLY_SHIPPED: frozenset({SHIPPED}),
    SHIPPED: frozenset(),
    CANCELLED: frozenset(),
}
"""合法流转：草稿→待确认/取消；待确认→待出库/取消；待出库→取消。已取消无出口。"""

EDITABLE_STATUSES = frozenset({DRAFT})
"""允许改客户、仓库、收货信息和明细的状态。目前只有草稿。"""

SUBMITTABLE_STATUSES = frozenset({DRAFT})
"""允许提交审核的状态。目前只有草稿。"""

CANCELLABLE_STATUSES = frozenset({DRAFT, PENDING_CONFIRMATION, WAITING_OUTBOUND})
"""允许整单取消的状态。一旦有正式出库（部分出库 / 已出库）不能再整单取消。"""


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
