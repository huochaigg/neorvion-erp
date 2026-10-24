from dataclasses import dataclass

from app.core.permissions import PermissionCode


@dataclass(frozen=True)
class ExecutionSpec:
    action_type: str
    schema_version: int
    risk_level: str
    permission: PermissionCode
    execute_path: str
    resource_type: str
    requires_approval: bool
    timeout_seconds: float
    max_reconcile_attempts: int


class ExecutionRegistry:
    """正式写入的封闭白名单；不暴露给 LLM Tool Registry。"""

    def __init__(self, specs: tuple[ExecutionSpec, ...]) -> None:
        self._specs = {item.action_type: item for item in specs}

    def get(self, action_type: str) -> ExecutionSpec:
        try:
            return self._specs[action_type]
        except KeyError as exc:
            raise ValueError("未注册的执行动作") from exc


def build_execution_registry() -> ExecutionRegistry:
    return ExecutionRegistry(
        (
            ExecutionSpec(
                "PURCHASE_ORDER_CREATE",
                1,
                "MEDIUM",
                PermissionCode.PURCHASE_CREATE,
                "/api/v1/action-executions/purchase-order",
                "PURCHASE_ORDER",
                False,
                15,
                3,
            ),
            ExecutionSpec(
                "SALES_ORDER_CREATE",
                1,
                "MEDIUM",
                PermissionCode.ORDER_CREATE,
                "/api/v1/action-executions/sales-order",
                "SALES_ORDER",
                False,
                15,
                3,
            ),
            ExecutionSpec(
                "INVENTORY_TRANSFER_CREATE",
                1,
                "HIGH",
                PermissionCode.STOCK_TRANSFER_CREATE,
                "/api/v1/action-executions/inventory-transfer",
                "STOCK_TRANSFER",
                True,
                15,
                3,
            ),
        )
    )
