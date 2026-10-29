from __future__ import annotations

from dataclasses import dataclass

from app.ai.types import ModelToolDefinition
from app.core.permissions import PermissionCode


@dataclass(frozen=True)
class ActionSpec:
    action_type: str
    description: str
    schema_version: int
    permission: PermissionCode
    resource_type: str
    risk_level: str
    preview_path: str
    required_fields: tuple[str, ...]
    editable_fields: tuple[str, ...]


class ActionRegistry:
    """业务动作白名单；只登记提案与预检地址，不包含任何 ERP 写入 Handler。"""

    def __init__(self, specs: tuple[ActionSpec, ...]) -> None:
        self._specs = {spec.action_type: spec for spec in specs}

    def get(self, action_type: str) -> ActionSpec:
        try:
            return self._specs[action_type]
        except KeyError as exc:
            raise ValueError("未注册的业务动作") from exc

    def all(self) -> tuple[ActionSpec, ...]:
        return tuple(self._specs.values())

    @property
    def names(self) -> frozenset[str]:
        """返回模型可见的 Proposal 工具名，用于跨注册表冲突检测。"""
        return frozenset({"propose_action", "validate_action_proposal"})

    @staticmethod
    def definitions(permissions: frozenset[str]) -> list[ModelToolDefinition]:
        """Proposal 工具定义与只读工具定义分离；服务端仍会再次鉴权。"""
        allowed = any(
            code in permissions
            for code in (
                PermissionCode.PURCHASE_CREATE,
                PermissionCode.ORDER_CREATE,
                PermissionCode.STOCK_TRANSFER_CREATE,
            )
        )
        if not allowed:
            return []
        from app.actions.schemas import ProposeActionArgs, ValidateActionProposalArgs

        return [
            {
                "type": "function",
                "function": {
                    "name": "propose_action",
                    "description": "创建结构化 ERP 业务草稿；字段不全时保留 NEEDS_INPUT，绝不执行真实业务写入。",
                    "parameters": ProposeActionArgs.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_action_proposal",
                    "description": "对当前用户已有的业务草稿执行 ERP 无副作用预检。",
                    "parameters": ValidateActionProposalArgs.model_json_schema(),
                },
            },
        ]


def build_action_registry() -> ActionRegistry:
    return ActionRegistry(
        (
            ActionSpec(
                "PURCHASE_ORDER_CREATE",
                "创建采购单草稿",
                1,
                PermissionCode.PURCHASE_CREATE,
                "PURCHASE_ORDER",
                "MEDIUM",
                "/api/v1/action-previews/purchase-order",
                ("supplier_id", "warehouse_id", "items"),
                ("supplier_id", "warehouse_id", "expected_arrival_date", "remark", "items"),
            ),
            ActionSpec(
                "SALES_ORDER_CREATE",
                "创建销售订单草稿",
                1,
                PermissionCode.ORDER_CREATE,
                "SALES_ORDER",
                "MEDIUM",
                "/api/v1/action-previews/sales-order",
                ("customer_id", "warehouse_id", "items"),
                (
                    "customer_id",
                    "warehouse_id",
                    "source",
                    "external_order_no",
                    "currency_code",
                    "recipient_name",
                    "recipient_phone",
                    "country_code",
                    "province",
                    "city",
                    "address",
                    "remark",
                    "items",
                ),
            ),
            ActionSpec(
                "INVENTORY_TRANSFER_CREATE",
                "创建库存调拨草稿",
                1,
                PermissionCode.STOCK_TRANSFER_CREATE,
                "STOCK_TRANSFER",
                "HIGH",
                "/api/v1/action-previews/inventory-transfer",
                ("source_warehouse_id", "target_warehouse_id", "items"),
                ("source_warehouse_id", "target_warehouse_id", "remark", "items"),
            ),
        )
    )
