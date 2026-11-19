from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.agents.router import AgentRouter

Intent = Literal["GENERAL_CHAT", "INVENTORY_ANALYSIS", "SALES_ANALYSIS", "ORDER_REVIEW", "KNOWLEDGE_RESEARCH", "PROCUREMENT_ANALYSIS", "WORKFLOW_REQUEST", "UNKNOWN"]
Complexity = Literal["SIMPLE", "COMPOSITE", "MULTI_DOMAIN"]
Risk = Literal["READ_ONLY", "DRAFT_WRITE", "APPROVAL_REQUIRED", "HIGH_RISK"]


@dataclass(frozen=True, slots=True)
class TaskClassification:
    """只提供路由信号；该结果绝不替代 IAM、Tool 或 Workflow 授权。"""

    intent: Intent
    complexity: Complexity
    risk: Risk
    domains: tuple[str, ...]
    negative_action: bool = False

    def as_dict(self) -> dict[str, object]:
        return {"intent": self.intent, "complexity": self.complexity, "risk": self.risk, "domains": list(self.domains), "negative_action": self.negative_action}


class TaskClassifier:
    """复用 V8 AgentRouter 的领域判断，并增加保守风险与复杂度分类。"""

    _write = re.compile(r"创建|新增|修改|删除|退款|发货|出库|入库|调拨|采购单|审批|执行")
    _draft = re.compile(r"草稿|建议单|预检|准备")
    _approve = re.compile(r"审批|确认执行|自动采购|自动退款|直接执行")
    _negative = re.compile(r"(?:不想|不要|别|禁止|不能|不会|不需要).{0,8}(?:删除|创建|修改|执行|审批|退款|采购)")
    _general = re.compile(r"^(?:你好|您好|谢谢|在吗|hello|hi)[！!。.\s]*$", re.I)

    def __init__(self, router: AgentRouter | None = None) -> None:
        self.router = router or AgentRouter()

    def classify(self, task: str) -> TaskClassification:
        text = task.strip()
        route = self.router.route(text)
        domains = tuple(name.removesuffix("_agent").upper() for name in route.agents)
        negative = bool(self._negative.search(text))
        if negative or not self._write.search(text):
            risk: Risk = "READ_ONLY"
        elif self._approve.search(text):
            risk = "APPROVAL_REQUIRED"
        elif self._draft.search(text):
            risk = "DRAFT_WRITE"
        else:
            risk = "HIGH_RISK"
        complexity: Complexity = "MULTI_DOMAIN" if len(domains) >= 2 else "COMPOSITE" if route.mode in {"multi", "workflow"} or any(x in text for x in ("并且", "同时", "然后", "再")) else "SIMPLE"
        intent: Intent
        if self._general.fullmatch(text):
            intent = "GENERAL_CHAT"
        elif route.mode == "workflow":
            intent = "WORKFLOW_REQUEST"
        elif "INVENTORY" in domains:
            intent = "INVENTORY_ANALYSIS"
        elif "KNOWLEDGE" in domains:
            intent = "KNOWLEDGE_RESEARCH"
        elif "PROCUREMENT" in domains:
            intent = "PROCUREMENT_ANALYSIS"
        elif "SALES" in domains and ("订单" in text or "order" in text.lower()):
            intent = "ORDER_REVIEW"
        elif "SALES" in domains:
            intent = "SALES_ANALYSIS"
        else:
            intent = "UNKNOWN"
        return TaskClassification(intent, complexity, risk, domains, negative)
