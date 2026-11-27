"""已有 Skill 版本与当前任务的能力匹配；召回分数不构成执行授权。"""

from __future__ import annotations

import re

from app.intent.query import describe_query


def assess_skill(task: str, allowed_tools: tuple[str, ...] | list[str], metadata: dict | None = None, allowed_agents: tuple[str, ...] | list[str] = (), input_schema: dict | None = None, *, skill_key: str | None = None) -> tuple[bool, str]:
    """依据固定版本的工具及可选能力元数据，在 InputCollector 前拒绝错误补参。"""
    query = describe_query(task)
    tools = set(allowed_tools)
    if allowed_agents and query.entity in {"sales_order", "customer"} and "sales_agent" not in allowed_agents:
        return False, "该 Skill 的 Agent 不支持销售领域"
    payload = metadata or {}
    nested = payload.get("metadata")
    capability_metadata = nested if isinstance(nested, dict) else payload
    domains = capability_metadata.get("domains")
    if isinstance(domains, list) and query.entity in {"sales_order", "customer"} and "SALES" not in {str(item).upper() for item in domains}:
        return False, "该 Skill 声明的领域不包含销售"
    declared = capability_metadata.get("query_shapes")
    if isinstance(declared, list) and query.shape not in declared:
        return False, f"该 Skill 不支持 {query.shape} 查询"
    if query.negative:
        return False, "当前消息否定了该查询任务"
    if skill_key == "sales-order-review" and not _review_task(task):
        return False, "订单审查 Skill 仅适用于明确要求审查订单的任务"
    if query.shape == "RANK" and "order_id" in (input_schema or {}).get("required", ()):
        return False, "排名任务不能由必填单笔订单主键的 Skill 执行"
    if query.entity == "sales_order" and query.shape == "RANK" and "list_sales_orders" not in tools:
        return False, "该 Skill 只能处理指定订单，无法对授权范围内的订单按金额排名"
    if query.entity == "sales_order" and query.shape == "DETAIL" and not tools.intersection({"get_sales_order", "list_sales_orders"}):
        return False, "该 Skill 没有订单详情或订单号定位能力"
    if query.entity == "customer" and query.shape == "RANK" and "get_top_sales_customers" not in tools:
        return False, "该 Skill 无法按客户累计销售金额排名"
    if query.shape in {"AGGREGATE", "COMPARE"} and query.metric == "total_amount" and not tools.intersection({"get_sales_summary", "get_sales_trend"}):
        return False, "该 Skill 不具备销售金额汇总能力"
    if query.shape == "TREND" and "get_sales_trend" not in tools:
        return False, "该 Skill 不具备趋势查询能力"
    if query.entity == "sales_order" and query.shape == "LIST" and "list_sales_orders" not in tools and not (_review_task(task) and "get_sales_order" in tools):
        return False, "该 Skill 仅能审查指定订单，不能执行列表查询"
    return True, "Skill 工具覆盖当前查询形态；执行时仍需 IAM 和 ToolPolicy 校验"


def _review_task(text: str) -> bool:
    return any(word in text for word in ("审查", "审核", "检查", "风险", "review"))


def pending_relation(text: str, *, missing_fields: list[str], skill_key: str) -> str:
    """辨别补参、会话取消与新任务；纯取消不等于 ERP 订单业务取消。"""
    stripped = text.strip()
    if any(word in stripped for word in ("算了，", "算了,", "不用了，", "不用了,")):
        return "NEW_TASK"
    if stripped in {"算了", "取消", "不用了", "停止", "取消刚才的查询", "取消刚才的订单查询"}:
        return "CANCEL"
    if "order_id" in missing_fields and (
        stripped.isdigit() or re.fullmatch(r"SO\d+", stripped, re.I)
    ):
        return "SUPPLEMENT"
    query = describe_query(stripped)
    if query.shape == "RANK" and query.metric == "total_amount":
        return "NEW_TASK"
    if skill_key == "sales-order-review" and query.entity == "sales_order" and _review_task(stripped):
        return "CONTINUE"
    if stripped.startswith(("改成", "改为", "换成")) and not any(word in stripped for word in ("订单", "客户", "销售")):
        return "MODIFY"
    if re.search(r"查询|查一下|哪个|多少|最高|最低|最大|最小|趋势|对比|排名", stripped):
        return "NEW_TASK"
    return "AMBIGUOUS"
