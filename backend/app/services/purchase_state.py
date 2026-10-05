"""采购单状态机。所有流转走这里，避免接口里散落 if status == ..."""

from app.core.exceptions import AppError
from app.models.purchase import PurchaseOrderStatus

DRAFT = PurchaseOrderStatus.DRAFT.value
PENDING_APPROVAL = PurchaseOrderStatus.PENDING_APPROVAL.value
WAITING_RECEIPT = PurchaseOrderStatus.WAITING_RECEIPT.value
REJECTED = PurchaseOrderStatus.REJECTED.value
CANCELLED = PurchaseOrderStatus.CANCELLED.value

# 不保留 APPROVED：审核通过同事务直接进入待收货，避免多余中间态。
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({PENDING_APPROVAL, CANCELLED}),
    PENDING_APPROVAL: frozenset({WAITING_RECEIPT, REJECTED, CANCELLED}),
    REJECTED: frozenset({PENDING_APPROVAL, CANCELLED}),
    WAITING_RECEIPT: frozenset(),
    CANCELLED: frozenset(),
}

EDITABLE_STATUSES = frozenset({DRAFT, REJECTED})
SUBMITTABLE_STATUSES = frozenset({DRAFT, REJECTED})
CANCELLABLE_STATUSES = frozenset({DRAFT, PENDING_APPROVAL, REJECTED})


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
