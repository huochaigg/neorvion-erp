"""V15 查询形态提取：只描述任务，不授予工具或数据权限。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueryShape:
    """查询口径；不清楚的字段留空，由现有理解层或执行层澄清。"""

    shape: str = "LIST"
    entity: str | None = None
    metric: str | None = None
    aggregation: str | None = None
    group_by: str | None = None
    sort_order: str | None = None
    limit: int | None = None
    currency_code: str | None = None
    time_range: str | None = None
    negative: bool = False


_rank = re.compile(r"最大|最高|最多|最贵|最大额|排名|前\s*[一二三四五六七八九十\d]+|top\s*\d+|最小|最低|最少|最便宜|后\s*[一二三四五六七八九十\d]+", re.I)
_min = re.compile(r"最小|最低|最少|最便宜|后\s*[一二三四五六七八九十\d]+")
_limit = re.compile(r"(?:前|后|top\s*)(\d+|[一二三四五六七八九十]+)", re.I)
_rank_count = re.compile(r"(?:最高|最低|最大|最小).{0,3}?(\d+|[一二三四五六七八九十]+)\s*(?:笔|个|条|名)")
_chinese_numbers = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def describe_query(text: str) -> QueryShape:
    """提取通用查询形态供 V15 Task 和 Skill 能力匹配复用；否定句不触发排名。"""
    parts = re.split(r"[，,；;]", text)
    if len(parts) > 1 and re.search(r"(?:查询|查|哪个|排名|金额|趋势)", parts[-1]):
        text = parts[-1]
    negative = bool(re.search(r"(?:不想|不要|别|无需|取消刚才).{0,12}(?:查|查询|排名)", text))
    entity = "sales_order" if "订单" in text or re.search(r"\bSO\d+\b", text, re.I) else "customer" if "客户" in text else None
    metric = "total_amount" if re.search(r"金额|销售额|采购金额|最贵|最便宜", text) else "order_count" if "数量" in text or "多少笔" in text else None
    currency = re.search(r"\b(CNY|USD|EUR|JPY|GBP)\b", text, re.I)
    currency_code = currency.group(1).upper() if currency else "USD" if "美元" in text else "CNY" if "人民币" in text else None
    date = re.search(r"最近[一二三四五六七八九十\d]+(?:天|个月)|本月|上月|昨天", text)
    order_code = re.search(r"\bSO\d+\b", text, re.I)
    primary_id = re.search(r"(?:订单主键|order[_ ]?id)\s*[:：#]?\s*\d+", text, re.I)
    if order_code or primary_id:
        shape = "DETAIL"
    elif not negative and _rank.search(text) and (metric or _limit.search(text)):
        shape = "RANK"
    elif not negative and re.search(r"趋势|走势|逐月|按月|逐日", text):
        shape = "TREND"
    elif not negative and re.search(r"对比|比较|环比", text):
        shape = "COMPARE"
    elif not negative and re.search(r"总金额|总额|总计|累计|多少笔|数量|销售额", text) and not re.search(r"列表|明细", text):
        shape = "AGGREGATE"
    else:
        shape = "LIST"
    match = _limit.search(text) or _rank_count.search(text)
    count = _chinese_numbers.get(match.group(1), 1) if match else 10 if "排名" in text else 1
    if match and match.group(1).isdigit():
        count = min(int(match.group(1)), 50)
    return QueryShape(
        shape=shape, entity=entity, metric=metric,
        aggregation="SUM" if shape in {"AGGREGATE", "RANK"} and entity == "customer" else None,
        group_by="customer_id" if shape == "RANK" and entity == "customer" else None,
        sort_order=("ASC" if _min.search(text) else "DESC") if shape == "RANK" else None,
        limit=count if shape == "RANK" else None,
        currency_code=currency_code,
        time_range=date.group(0) if date else None,
        negative=negative,
    )
