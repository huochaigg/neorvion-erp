"""采购退货状态机。所有流转走这里，避免接口里散落 if status == ..."""

from app.core.exceptions import AppError
from app.models.purchase_return import PurchaseReturnStatus

DRAFT = PurchaseReturnStatus.DRAFT.value
PENDING_APPROVAL = PurchaseReturnStatus.PENDING_APPROVAL.value
WAITING_OUTBOUND = PurchaseReturnStatus.WAITING_OUTBOUND.value
PARTIALLY_RETURNED = PurchaseReturnStatus.PARTIALLY_RETURNED.value
WAITING_REFUND = PurchaseReturnStatus.WAITING_REFUND.value
COMPLETED = PurchaseReturnStatus.COMPLETED.value
REJECTED = PurchaseReturnStatus.REJECTED.value
CANCELLED = PurchaseReturnStatus.CANCELLED.value

# 不保留 APPROVED / RETURNED / REFUNDED：审核通过同事务进入待出库；
# 全部出库后按结算类型直接 COMPLETED 或 WAITING_REFUND。
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({PENDING_APPROVAL, CANCELLED}),
    PENDING_APPROVAL: frozenset({WAITING_OUTBOUND, REJECTED, CANCELLED}),
    WAITING_OUTBOUND: frozenset({PARTIALLY_RETURNED, WAITING_REFUND, COMPLETED}),
    PARTIALLY_RETURNED: frozenset({PARTIALLY_RETURNED, WAITING_REFUND, COMPLETED}),
    WAITING_REFUND: frozenset({COMPLETED}),
    COMPLETED: frozenset(),
    REJECTED: frozenset(),
    CANCELLED: frozenset(),
}

EDITABLE_STATUSES = frozenset({DRAFT})
SUBMITTABLE_STATUSES = frozenset({DRAFT})
CANCELLABLE_STATUSES = frozenset({DRAFT, PENDING_APPROVAL})
OUTBOUND_STATUSES = frozenset({WAITING_OUTBOUND, PARTIALLY_RETURNED})
# DRAFT 不占用可退数量，提交审核后开始占用。
OCCUPY_STATUSES = frozenset(
    {
        PENDING_APPROVAL,
        WAITING_OUTBOUND,
        PARTIALLY_RETURNED,
        WAITING_REFUND,
        COMPLETED,
    }
)


def can_transition(current: str, target: str) -> bool:
    allowed = ALLOWED_TRANSITIONS.get(current)
    return allowed is not None and target in allowed


def require_transition(current: str, target: str) -> None:
    """非法流转必须拒绝。前端藏按钮只是体验，服务端才是规则。"""
    if not can_transition(current, target):
        raise AppError(
            f"当前状态不能从 {current} 变更为 {target}",
            code=40354,
            status_code=400,
            data={"error": "INVALID_PURCHASE_RETURN_TRANSITION", "from": current, "to": target},
        )
