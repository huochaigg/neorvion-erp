"""Intent Registry：唯一键、类型、槽位和能力映射校验。它不是权限源。"""

from __future__ import annotations

from functools import lru_cache

from app.intent.catalog import INTENT_DEFINITIONS
from app.intent.schemas import IntentDefinition, ProblemType

KNOWN_AGENTS = frozenset(
    {
        "sales_agent",
        "inventory_agent",
        "procurement_agent",
        "knowledge_agent",
        "supervisor_agent",
    }
)
KNOWN_SKILLS = frozenset(
    {
        "inventory-analysis",
        "sales-order-review",
        "knowledge-research",
    }
)
KNOWN_TOOLS = frozenset(
    {
        "get_sales_order",
        "list_sales_orders",
        "get_inventory",
        "get_product",
        "search_products",
        "list_purchase_orders",
        "get_warehouse",
        "get_after_sale",
        "list_knowledge_bases",
        "search_knowledge",
        "analyze_inventory_coverage",
        "propose_action",
        "validate_action_proposal",
    }
)
ANALYSIS_SKILLS = frozenset({"inventory-analysis", "sales-order-review"})
WRITE_TOOLS = frozenset({"propose_action", "validate_action_proposal"})


class IntentRegistry:
    """内存注册表。V15 不引入独立数据库表，避免把 Intent 做成第二套权限系统。"""

    def __init__(self, definitions: tuple[IntentDefinition, ...] | None = None) -> None:
        items = definitions if definitions is not None else INTENT_DEFINITIONS
        self._items = self._validate(items)

    @staticmethod
    def _validate(items: tuple[IntentDefinition, ...]) -> dict[str, IntentDefinition]:
        output: dict[str, IntentDefinition] = {}
        for item in items:
            if item.intent_key in output:
                raise ValueError(f"重复的 intent_key: {item.intent_key}")
            overlap = set(item.required_slots) & set(item.optional_slots)
            if overlap:
                raise ValueError(f"{item.intent_key} 的槽位同时出现在必填和可选：{sorted(overlap)}")
            unknown_agents = set(item.candidate_agents) - KNOWN_AGENTS
            if unknown_agents:
                raise ValueError(f"{item.intent_key} 映射了未注册 Agent: {sorted(unknown_agents)}")
            unknown_skills = set(item.candidate_skills) - KNOWN_SKILLS
            if unknown_skills:
                raise ValueError(f"{item.intent_key} 映射了未注册 Skill: {sorted(unknown_skills)}")
            unknown_tools = set(item.capability_hints) - KNOWN_TOOLS
            if unknown_tools:
                raise ValueError(f"{item.intent_key} 映射了未注册 Tool: {sorted(unknown_tools)}")
            if item.problem_type == "ACTION" and item.executable and not item.capability_hints:
                raise ValueError(f"{item.intent_key} 声称可执行但没有 capability_hints")
            if not item.executable and item.capability_hints:
                raise ValueError(f"{item.intent_key} 不可执行却声明了执行能力")
            output[item.intent_key] = item
        return output

    def get(self, intent_key: str) -> IntentDefinition | None:
        item = self._items.get(intent_key)
        if item is None or not item.enabled:
            return None
        return item

    def require(self, intent_key: str) -> IntentDefinition:
        item = self.get(intent_key)
        if item is None:
            raise KeyError(intent_key)
        return item

    def contains(self, intent_key: str) -> bool:
        return self.get(intent_key) is not None

    def enabled(self) -> tuple[IntentDefinition, ...]:
        return tuple(item for item in self._items.values() if item.enabled)

    def keys(self) -> frozenset[str]:
        return frozenset(item.intent_key for item in self.enabled())

    def by_problem_type(self, problem_type: ProblemType) -> tuple[IntentDefinition, ...]:
        return tuple(item for item in self.enabled() if item.problem_type == problem_type)


@lru_cache
def get_intent_registry() -> IntentRegistry:
    return IntentRegistry()
