from __future__ import annotations

from dataclasses import dataclass

from app.core.permissions import PermissionCode


@dataclass(frozen=True, slots=True)
class WorkflowStepSpec:
    key: str
    step_type: str
    failure_policy: str


@dataclass(frozen=True, slots=True)
class WorkflowSpec:
    workflow_type: str
    schema_version: int
    description: str
    permissions: tuple[str, ...]
    steps: tuple[WorkflowStepSpec, ...]
    max_steps: int
    compensation_policy: str


class WorkflowRegistry:
    """确定性的长流程白名单；模型和客户端都不能构造任意 Graph。"""

    def __init__(self, specs: tuple[WorkflowSpec, ...]) -> None:
        self._specs = {item.workflow_type: item for item in specs}

    def get(self, workflow_type: str) -> WorkflowSpec:
        try:
            return self._specs[workflow_type]
        except KeyError as exc:
            raise ValueError("未注册的工作流") from exc

    def all(self) -> tuple[WorkflowSpec, ...]:
        return tuple(self._specs.values())


def build_workflow_registry() -> WorkflowRegistry:
    return WorkflowRegistry(
        (
            WorkflowSpec(
                "INVENTORY_REPLENISHMENT_WORKFLOW",
                1,
                "库存分析与受控采购草稿流程",
                (
                    PermissionCode.PRODUCT_READ.value,
                    PermissionCode.INVENTORY_READ.value,
                    PermissionCode.ANALYTICS_SALES_READ.value,
                ),
                (
                    WorkflowStepSpec("validate_input", "VALIDATE", "WAIT_INPUT"),
                    WorkflowStepSpec("inventory_analysis", "ERP_READ", "RETRY"),
                    WorkflowStepSpec("knowledge_rules", "KNOWLEDGE_READ", "CONTINUE_WITH_WARNING"),
                    WorkflowStepSpec("purchase_input", "HUMAN_INPUT", "WAIT_INPUT"),
                    WorkflowStepSpec("proposal", "PROPOSAL", "RETRY"),
                    WorkflowStepSpec("execution", "V6_EXECUTION", "RECONCILE"),
                    WorkflowStepSpec("finalize", "FINALIZE", "MANUAL"),
                ),
                12,
                "MANUAL_IF_ERP_CREATED",
            ),
            WorkflowSpec(
                "SALES_ORDER_REVIEW_WORKFLOW",
                1,
                "销售订单出库条件只读审查",
                (PermissionCode.ORDER_READ.value, PermissionCode.INVENTORY_READ.value),
                (
                    WorkflowStepSpec("validate_input", "VALIDATE", "WAIT_INPUT"),
                    WorkflowStepSpec("order_lookup", "ERP_READ", "RETRY"),
                    WorkflowStepSpec("knowledge_rules", "KNOWLEDGE_READ", "CONTINUE_WITH_WARNING"),
                    WorkflowStepSpec("risk_analysis", "DETERMINISTIC_ANALYSIS", "MANUAL"),
                    WorkflowStepSpec("finalize", "FINALIZE", "MANUAL"),
                ),
                10,
                "READ_ONLY_NONE",
            ),
        )
    )
