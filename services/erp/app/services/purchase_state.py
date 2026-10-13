"""采购单状态机。所有流转走这里，避免接口里散落 if status == ..."""

from app.core.exceptions import AppError
from app.models.purchase import PurchaseOrderStatus

DRAFT = PurchaseOrderStatus.DRAFT.value
"""草稿。可改单；可提交或取消。未入库。"""

PENDING_APPROVAL = PurchaseOrderStatus.PENDING_APPROVAL.value
"""待审核。可批准、驳回或取消。批准同事务进入待收货。"""

WAITING_RECEIPT = PurchaseOrderStatus.WAITING_RECEIPT.value
"""待收货。审核已通过，等收货入库。本版本不可取消。"""

PARTIALLY_RECEIVED = PurchaseOrderStatus.PARTIALLY_RECEIVED.value
"""部分收货。已入库一部分，还可继续收。"""

RECEIVED = PurchaseOrderStatus.RECEIVED.value
"""已收货。全部收齐。终态。"""

REJECTED = PurchaseOrderStatus.REJECTED.value
"""已驳回。可改后重提，或取消。"""

CANCELLED = PurchaseOrderStatus.CANCELLED.value
"""已取消。终态。"""

# 不保留 APPROVED：审核通过同事务直接进入待收货。
# 部分收货 / 收完由收货确认写入，不提供任意改状态接口。
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({PENDING_APPROVAL, CANCELLED}),
    PENDING_APPROVAL: frozenset({WAITING_RECEIPT, REJECTED, CANCELLED}),
    REJECTED: frozenset({PENDING_APPROVAL, CANCELLED}),
    WAITING_RECEIPT: frozenset({PARTIALLY_RECEIVED, RECEIVED}),
    PARTIALLY_RECEIVED: frozenset({RECEIVED}),
    RECEIVED: frozenset(),
    CANCELLED: frozenset(),
}
"""合法流转。待收货/部分收货靠收货确认推进；已收货与已取消无出口。"""

RECEIVABLE_STATUSES = frozenset({WAITING_RECEIPT, PARTIALLY_RECEIVED})
"""允许创建/确认收货单的状态。"""

EDITABLE_STATUSES = frozenset({DRAFT, REJECTED})
"""允许改供应商、仓库和明细的状态。"""

SUBMITTABLE_STATUSES = frozenset({DRAFT, REJECTED})
"""允许提交审核的状态。"""

CANCELLABLE_STATUSES = frozenset({DRAFT, PENDING_APPROVAL, REJECTED})
"""允许取消的状态。待收货及之后不可取消。"""


def can_transition(current: str, target: str) -> bool:
    allowed = ALLOWED_TRANSITIONS.get(current)
    return allowed is not None and target in allowed


def require_transition(current: str, target: str) -> None:
    """非法流转必须拒绝。前端藏按钮只是体验，服务端才是规则。"""
    if not can_transition(current, target):
        raise AppError(
            f"当前状态不能从 {current} 变更为 {target}",
            code=40090,
            status_code=400,
            data={"error": "INVALID_PURCHASE_ORDER_TRANSITION", "from": current, "to": target},
        )


def require_editable(status: str) -> None:
    if status not in EDITABLE_STATUSES:
        raise AppError(
            "当前状态不能修改供应商、仓库或采购明细",
            code=40091,
            status_code=400,
            data={"error": "PURCHASE_ORDER_NOT_EDITABLE"},
        )
