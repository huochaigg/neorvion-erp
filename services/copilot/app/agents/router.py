from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class AgentRoute:
    mode: Literal["single", "multi", "workflow"]
    agents: tuple[str, ...]
    reason: str


class AgentRouter:
    """使用确定性低权限规则选择模式；不确定时回退 Single Agent。"""

    _domains = {
        "sales_agent": ("销售", "订单", "销量", "履约", "售后", "出库"),
        "inventory_agent": ("库存", "仓库", "可用", "sku", "商品", "缺货"),
        "procurement_agent": ("采购", "供应商", "补货", "进货"),
        "knowledge_agent": ("知识库", "制度", "规则", "规定", "流程"),
    }
    _workflow_words = ("准备采购单", "生成采购单", "创建采购单", "启动工作流")
    _complex_words = ("分析", "为什么", "原因", "综合", "对比", "建议", "计划", "异常")

    def route(self, query: str) -> AgentRoute:
        lowered = query.strip().lower()
        if "无法出库" in lowered:
            return AgentRoute(
                "multi",
                ("sales_agent", "inventory_agent", "knowledge_agent"),
                "订单出库跨领域诊断",
            )
        matched = tuple(
            name for name, words in self._domains.items() if any(word in lowered for word in words)
        )
        if any(word in lowered for word in self._workflow_words):
            return AgentRoute("workflow", matched or ("procurement_agent",), "受控业务动作")
        complex_query = any(word in lowered for word in self._complex_words)
        if len(matched) >= 2 and complex_query:
            return AgentRoute("multi", matched, "跨领域复杂分析")
        return AgentRoute("single", matched[:1], "简单或单领域请求")
