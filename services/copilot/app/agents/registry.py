from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode


@dataclass(frozen=True, slots=True)
class AgentSpec:
    agent_name: str
    agent_version: int
    description: str
    domain: str
    allowed_tools: frozenset[str]
    required_permissions: tuple[str, ...]
    context_policy: str
    timeout_seconds: float
    max_tool_calls: int
    max_model_calls: int
    token_budget: int
    concurrency_policy: str = "parallel_safe"
    enabled: bool = True


class AgentRegistry:
    """可信代码定义的专业 Agent 注册表，不接受模型或客户端动态扩展。"""

    def __init__(
        self, specs: list[AgentSpec], *, known_tools: Collection[str] | None = None
    ) -> None:
        names = [item.agent_name for item in specs]
        if len(names) != len(set(names)):
            raise ValueError("Agent 名称重复")
        if known_tools is not None:
            invalid = {
                tool for spec in specs for tool in spec.allowed_tools if tool not in known_tools
            }
            if invalid:
                raise ValueError(f"Agent 引用了未注册工具：{', '.join(sorted(invalid))}")
        self._specs = {item.agent_name: item for item in specs}

    def get(self, name: str) -> AgentSpec:
        spec = self._specs.get(name)
        if spec is None or not spec.enabled:
            raise AppError("Agent 未注册或未启用", code=40088, status_code=400)
        return spec

    def all(self) -> tuple[AgentSpec, ...]:
        return tuple(self._specs.values())


def build_agent_registry() -> AgentRegistry:
    from app.tools.registry import build_tool_registry

    specs = [
        AgentSpec(
            "sales_agent",
            1,
            "销售订单、履约、销量与售后分析",
            "SALES",
            frozenset(
                {
                    "get_sales_order",
                    "list_sales_orders",
                    "get_after_sale",
                    "analyze_inventory_coverage",
                }
            ),
            (PermissionCode.ORDER_READ.value,),
            "latest_user_query_only",
            20,
            4,
            2,
            3000,
        ),
        AgentSpec(
            "inventory_agent",
            1,
            "商品、SKU、仓库、库存与覆盖分析",
            "INVENTORY",
            frozenset(
                {
                    "get_inventory",
                    "get_product",
                    "search_products",
                    "get_warehouse",
                    "analyze_inventory_coverage",
                }
            ),
            (PermissionCode.INVENTORY_READ.value,),
            "latest_user_query_only",
            20,
            4,
            2,
            3000,
        ),
        AgentSpec(
            "procurement_agent",
            1,
            "采购历史、供应信息与补货建议",
            "PROCUREMENT",
            frozenset(
                {
                    "list_purchase_orders",
                    "get_inventory",
                    "get_product",
                    "search_products",
                    "analyze_inventory_coverage",
                }
            ),
            (PermissionCode.PURCHASE_READ.value,),
            "latest_user_query_only",
            20,
            4,
            2,
            3000,
        ),
        AgentSpec(
            "knowledge_agent",
            1,
            "授权知识库规则检索与可验证引用",
            "KNOWLEDGE",
            frozenset({"list_knowledge_bases", "search_knowledge"}),
            (PermissionCode.KNOWLEDGE_READ.value,),
            "latest_user_query_only",
            20,
            3,
            2,
            3000,
        ),
        AgentSpec(
            "supervisor_agent",
            1,
            "汇总结构化专业结果并识别冲突",
            "SUPERVISOR",
            frozenset(),
            (),
            "structured_results_only",
            25,
            0,
            1,
            4000,
            concurrency_policy="coordinator",
        ),
    ]
    return AgentRegistry(specs, known_tools=build_tool_registry().names)
