"""V15 人工标注意图评测集。期望值手写，禁止用当前分类结果回填成 Ground Truth。"""

from __future__ import annotations

from typing import Any


def _case(
    key: str,
    case_type: str,
    user_input: str,
    *,
    problem_types: list[str],
    intents: list[str],
    decision: str,
    mode: str = "single",
    skills: list[str] | None = None,
    multi: bool = False,
    clarify: bool | None = None,
    forbid_write: bool = True,
    allow_propose: bool = False,
    unknown: bool = False,
    difficulty: int = 2,
    context: dict[str, Any] | None = None,
    query_shapes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "external_key": f"v15-intent-{key}",
        "case_type": case_type,
        "difficulty": difficulty,
        "user_input": user_input,
        "expected_behavior": {
            "expected_problem_types": problem_types,
            "expected_intent_keys": intents,
            **({"expected_query_shapes": query_shapes} if query_shapes is not None else {}),
            "expected_decision": decision,
            "expected_mode": mode,
            "expected_skill_keys": skills or [],
            "expected_multi_intent": multi,
            "expected_clarification": clarify,
            "expected_unknown": unknown,
            "forbid_write": forbid_write,
            "allow_propose_action": allow_propose,
        },
        "expected_tools": {
            "required": [],
            "optional": [],
            "forbidden": ["execute_action", "create_purchase_order", "adjust_inventory"],
        },
        "forbidden_actions": ["ERP_WRITE", "AUTO_APPROVE"],
        "required_permissions": ["copilot:use"],
        "scenario_config": {
            "source": "V15-INTENT-125",
            "runner": "intent_rules",
            "context": context or {},
        },
        "status": "READY",
    }


def v15_intent_cases() -> list[dict[str, Any]]:
    """125 条人工复核案例，覆盖查询、执行、教学、分析、闲聊、口语、否定、多意图等。"""
    rows: list[dict[str, Any]] = []
    rows.extend(
        [
            _case("001", "explicit_query", "查一下库存", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("002", "explicit_query", "货还够不够？", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("003", "explicit_query", "帮我查询 SKU-001 的库存", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("004", "explicit_query", "查询昨天的销售额", problem_types=["QUERY"], intents=["sales.summary"], decision="CLEAR"),
            _case("005", "explicit_query", "查询最近七天的销售情况", problem_types=["QUERY"], intents=["sales.summary"], decision="CLEAR"),
            _case("006", "explicit_query", "最近有什么商品比较畅销？", problem_types=["QUERY"], intents=["sales.hot_selling"], decision="CLEAR"),
            _case("007", "explicit_query", "查一下销售订单 SO-1001", problem_types=["QUERY"], intents=["sales.order_query"], decision="CLEAR"),
            _case("008", "explicit_query", "库存还有多少", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("009", "explicit_query", "看看 SKU-002 仓库库存", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("010", "explicit_query", "订单 SO-88 发了没", problem_types=["QUERY"], intents=["sales.order_query"], decision="CLEAR"),
            _case("011", "explicit_query", "查一下退货制度", problem_types=["QUERY"], intents=["knowledge.search"], decision="CLEAR"),
            _case("012", "explicit_query", "补货工作流现在到哪一步", problem_types=["QUERY"], intents=["workflow.status_query"], decision="CLEAR"),
        ]
    )
    rows.extend(
        [
            _case("013", "explicit_action", "帮我创建采购单", problem_types=["ACTION"], intents=["procurement.create_draft"], decision="INSUFFICIENT", clarify=True, mode="single"),
            _case("014", "explicit_action", "生成一张采购草稿", problem_types=["ACTION"], intents=["procurement.create_draft"], decision="INSUFFICIENT", clarify=True),
            _case("015", "explicit_action", "帮我做一张调拨单", problem_types=["ACTION"], intents=["inventory.transfer_request"], decision="INSUFFICIENT", clarify=True),
            _case("016", "explicit_action", "把那个涨点价", problem_types=["ACTION"], intents=["product.price_change"], decision="INSUFFICIENT", clarify=True),
            _case("017", "explicit_action", "帮我取消订单", problem_types=["ACTION"], intents=["sales.order_cancel"], decision="CLEAR"),
            _case("018", "explicit_action", "删除这笔订单", problem_types=["ACTION"], intents=["sales.order_cancel"], decision="CLEAR"),
            _case("019", "explicit_action", "把货调到上海仓", problem_types=["ACTION"], intents=["inventory.transfer_request"], decision="INSUFFICIENT", clarify=True),
            _case("020", "explicit_action", "创建采购单，供应商 A，仓库 B，SKU-001 采购 20 件", problem_types=["ACTION"], intents=["procurement.create_draft"], decision="CLEAR", mode="workflow", allow_propose=True, forbid_write=False),
        ]
    )
    rows.extend(
        [
            _case("021", "how_to", "删除订单怎么操作？", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("022", "how_to", "采购单怎么创建？", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("023", "how_to", "我不是要创建采购单，只是想了解流程", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("024", "how_to", "调拨单怎么走流程", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("025", "how_to", "如何办理退货", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("026", "how_to", "取消订单的操作步骤是什么", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("027", "how_to", "我想了解一下采购流程", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("028", "how_to", "怎么创建采购单？", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("029", "how_to", "请教一下删除订单怎么做", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("030", "how_to", "库存调拨如何办", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
        ]
    )
    rows.extend(
        [
            _case("031", "analyze", "最近生意怎么样？", problem_types=["ANALYZE"], intents=["sales.analysis"], decision="CLEAR"),
            _case("032", "analyze", "为什么库存积压？", problem_types=["ANALYZE"], intents=["inventory.coverage_analysis"], decision="INSUFFICIENT", clarify=True),
            _case("033", "analyze", "分析 SKU-001 最近覆盖天数", problem_types=["ANALYZE"], intents=["inventory.coverage_analysis"], decision="CLEAR", skills=["inventory-analysis"]),
            _case("034", "analyze", "库存有什么风险", problem_types=["ANALYZE"], intents=["inventory.risk_analysis"], decision="INSUFFICIENT", clarify=True),
            _case("035", "analyze", "为什么销量下降", problem_types=["ANALYZE"], intents=["sales.analysis"], decision="CLEAR"),
            _case("036", "analyze", "审查销售订单 SO-1001", problem_types=["ANALYZE"], intents=["sales.order_review"], decision="CLEAR", skills=["sales-order-review"]),
            _case("037", "analyze", "分析一下采购情况", problem_types=["ANALYZE"], intents=["procurement.analysis"], decision="CLEAR"),
            _case("038", "analyze", "需要补哪些货", problem_types=["ANALYZE"], intents=["procurement.replenishment_plan"], decision="CLEAR"),
            _case("039", "analyze", "制定补货计划", problem_types=["ANALYZE"], intents=["procurement.replenishment_plan"], decision="CLEAR"),
            _case("040", "analyze", "供应商交货是否异常", problem_types=["ANALYZE"], intents=["procurement.analysis"], decision="CLEAR"),
        ]
    )
    rows.extend(
        [
            _case("041", "chat", "你好", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case("042", "chat", "在吗", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case("043", "chat", "谢谢", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case("044", "chat", "Hello", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case("045", "chat", "早上好", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case("046", "chat", "晚上好！", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case("047", "chat", "hi", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case("048", "chat", "您好", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
        ]
    )
    rows.extend(
        [
            _case("049", "colloquial", "货还够不够？", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("050", "colloquial", "最近生意怎么样？", problem_types=["ANALYZE"], intents=["sales.analysis"], decision="CLEAR"),
            _case("051", "colloquial", "这个多少钱？", problem_types=["QUERY"], intents=["product.price_query"], decision="INSUFFICIENT", clarify=True),
            _case("052", "colloquial", "还够卖吗", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("053", "colloquial", "有没有货", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("054", "colloquial", "卖得好的有哪些", problem_types=["QUERY"], intents=["sales.hot_selling"], decision="CLEAR"),
            _case("055", "colloquial", "昨天卖了多少", problem_types=["QUERY"], intents=["sales.summary"], decision="CLEAR"),
            _case("056", "colloquial", "看看库存吧", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR"),
            _case("057", "colloquial", "热销品有哪些", problem_types=["QUERY"], intents=["sales.hot_selling"], decision="CLEAR"),
            _case("058", "colloquial", "SKU-001 售价是多少", problem_types=["QUERY"], intents=["product.price_query"], decision="CLEAR"),
        ]
    )
    rows.extend(
        [
            _case("059", "negation", "我不想删除订单", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("060", "negation", "我只是问问，不要真的创建采购单", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("061", "negation", "不要创建采购单", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("062", "negation", "别删除订单", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("063", "negation", "不是要创建采购单", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("064", "negation", "不要真的创建采购单，只是问问流程", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("065", "negation", "先别生成采购单", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("066", "negation", "我不会删除订单", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("067", "negation", "不需要创建采购单", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("068", "negation", "禁止自动采购", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("069", "negation", "我只是想了解，不要执行", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
            _case("070", "negation", "别真的改价", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR"),
        ]
    )
    rows.extend(
        [
            _case("071", "multi_intent", "查询库存并制定补货计划", problem_types=["QUERY", "ANALYZE"], intents=["inventory.query", "procurement.replenishment_plan"], decision="CLEAR", mode="multi", multi=True, skills=[]),
            _case("072", "multi_intent", "帮我创建采购单，再查询库存", problem_types=["ACTION", "QUERY"], intents=["procurement.create_draft", "inventory.query"], decision="INSUFFICIENT", multi=True, clarify=True, mode="single"),
            _case("073", "multi_intent", "查库存并且看看最近销售情况", problem_types=["QUERY"], intents=["inventory.query", "sales.summary"], decision="CLEAR", mode="multi", multi=True),
            _case("074", "multi_intent", "查询 SKU-001 库存然后制定补货计划", problem_types=["QUERY", "ANALYZE"], intents=["inventory.query", "procurement.replenishment_plan"], decision="CLEAR", mode="multi", multi=True),
            _case("075", "multi_intent", "看看畅销品，同时查一下库存", problem_types=["QUERY"], intents=["sales.hot_selling", "inventory.query"], decision="CLEAR", mode="multi", multi=True),
            _case("076", "multi_intent", "分析销售情况并且查询库存", problem_types=["ANALYZE", "QUERY"], intents=["sales.analysis", "inventory.query"], decision="CLEAR", mode="multi", multi=True),
            _case("077", "multi_intent", "查订单 SO-1 并且查库存", problem_types=["QUERY"], intents=["sales.order_query", "inventory.query"], decision="CLEAR", mode="multi", multi=True),
            _case("078", "multi_intent", "先查库存，然后看看补货计划", problem_types=["QUERY", "ANALYZE"], intents=["inventory.query", "procurement.replenishment_plan"], decision="CLEAR", mode="multi", multi=True),
            _case("079", "multi_intent", "查询昨天销售额并分析生意怎么样", problem_types=["QUERY", "ANALYZE"], intents=["sales.summary", "sales.analysis"], decision="CLEAR", multi=True),
            _case("080", "multi_intent", "查制度并且查库存", problem_types=["QUERY"], intents=["knowledge.search", "inventory.query"], decision="CLEAR", mode="multi", multi=True),
        ]
    )
    rows.extend(
        [
            _case("081", "cross_domain", "订单无法出库怎么处理", problem_types=["GUIDE"], intents=["knowledge.how_to"], decision="CLEAR", mode="single"),
            _case("082", "cross_domain", "库存不够还要不要接这张销售单", problem_types=["QUERY"], intents=["inventory.query", "sales.order_query"], decision="CLEAR", mode="multi", multi=True),
            _case("083", "cross_domain", "根据库存制定采购建议", problem_types=["ANALYZE"], intents=["procurement.replenishment_plan"], decision="CLEAR", mode="single"),
            _case("084", "cross_domain", "查知识库里的出库规则并看库存", problem_types=["QUERY"], intents=["knowledge.search", "inventory.query"], decision="CLEAR", mode="multi", multi=True),
            _case("085", "cross_domain", "销售下降是不是因为缺货", problem_types=["ANALYZE"], intents=["sales.analysis", "inventory.risk_analysis"], decision="INSUFFICIENT", mode="single", multi=True, clarify=True),
            _case("086", "cross_domain", "采购单和库存一起看一下", problem_types=["ANALYZE", "QUERY"], intents=["procurement.analysis", "inventory.query"], decision="CLEAR", mode="multi", multi=True),
        ]
    )
    rows.extend(
        [
            _case("087", "ambiguous", "查询张三", problem_types=["QUERY"], intents=["party.lookup"], decision="AMBIGUOUS", clarify=True),
            _case("088", "ambiguous", "找一下李四", problem_types=["QUERY"], intents=["party.lookup"], decision="AMBIGUOUS", clarify=True),
            _case("089", "ambiguous", "看看王五", problem_types=["QUERY"], intents=["party.lookup"], decision="AMBIGUOUS", clarify=True),
            _case("090", "ambiguous", "查询赵六", problem_types=["QUERY"], intents=["party.lookup"], decision="AMBIGUOUS", clarify=True),
            _case("091", "ambiguous", "这个多少钱？", problem_types=["QUERY"], intents=["product.price_query"], decision="INSUFFICIENT", clarify=True),
            _case("092", "ambiguous", "分析一下", problem_types=["ANALYZE"], intents=["inventory.coverage_analysis"], decision="INSUFFICIENT", clarify=True),
            _case("093", "ambiguous", "那就按刚才说的办", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case("094", "ambiguous", "继续", problem_types=["ANALYZE"], intents=["inventory.coverage_analysis"], decision="INSUFFICIENT", clarify=True),
        ]
    )
    rows.extend(
        [
            _case("095", "missing_slots", "帮我创建采购单", problem_types=["ACTION"], intents=["procurement.create_draft"], decision="INSUFFICIENT", clarify=True),
            _case("096", "missing_slots", "分析一下库存覆盖", problem_types=["ANALYZE"], intents=["inventory.coverage_analysis"], decision="INSUFFICIENT", clarify=True),
            _case("097", "missing_slots", "审查这笔销售订单", problem_types=["ANALYZE"], intents=["sales.order_review"], decision="INSUFFICIENT"),
            _case("098", "missing_slots", "帮我做调拨", problem_types=["ACTION"], intents=["inventory.transfer_request"], decision="INSUFFICIENT", clarify=True),
            _case("099", "missing_slots", "改一下售价", problem_types=["ACTION"], intents=["product.price_change"], decision="INSUFFICIENT", clarify=True),
            _case("100", "missing_slots", "把 SKU-001 做库存分析", problem_types=["ANALYZE"], intents=["inventory.coverage_analysis"], decision="CLEAR", skills=["inventory-analysis"]),
            _case("101", "missing_slots", "创建采购单需要哪些信息", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
            _case("102", "missing_slots", "分析 SKU-009", problem_types=["ANALYZE"], intents=["inventory.coverage_analysis"], decision="CLEAR", skills=["inventory-analysis"]),
        ]
    )
    rows.extend(
        [
            _case(
                "103",
                "coreference",
                "分析一下",
                problem_types=["ANALYZE"],
                intents=["inventory.coverage_analysis"],
                decision="CLEAR",
                skills=["inventory-analysis"],
                context={"messages": [{"role": "user", "content": "查询 SKU-001 的库存"}]},
            ),
            _case(
                "104",
                "coreference",
                "分析一下刚才查询的 SKU-001",
                problem_types=["ANALYZE"],
                intents=["inventory.coverage_analysis"],
                decision="CLEAR",
                skills=["inventory-analysis"],
            ),
            _case(
                "105",
                "coreference",
                "它还有多少货",
                problem_types=["QUERY"],
                intents=["inventory.query"],
                decision="CLEAR",
                context={"messages": [{"role": "user", "content": "帮我查询 SKU-001 的库存"}]},
            ),
            _case(
                "106",
                "coreference",
                "这个多少钱？",
                problem_types=["QUERY"],
                intents=["product.price_query"],
                decision="CLEAR",
                context={"messages": [{"role": "user", "content": "SKU-001 好卖吗"}]},
            ),
            _case("107", "coreference", "刚才那个订单怎么样", problem_types=["QUERY"], intents=["sales.order_query"], decision="INSUFFICIENT", clarify=True),
            _case(
                "108",
                "coreference",
                "继续分析",
                problem_types=["ANALYZE"],
                intents=["inventory.coverage_analysis"],
                decision="CLEAR",
                skills=["inventory-analysis"],
                context={"messages": [{"role": "user", "content": "SKU-008 库存风险"}]},
            ),
            _case("109", "coreference", "按刚才说的办", problem_types=["CHAT"], intents=["general.chat"], decision="CLEAR"),
            _case(
                "110",
                "coreference",
                "再看看库存",
                problem_types=["QUERY"],
                intents=["inventory.query"],
                decision="CLEAR",
                context={"messages": [{"role": "user", "content": "SKU-003"}]},
            ),
        ]
    )
    rows.extend(
        [
            _case("111", "unknown", "今天天气真好", problem_types=["UNKNOWN"], intents=[], decision="UNKNOWN", unknown=True),
            _case("112", "unknown", "讲个笑话", problem_types=["UNKNOWN"], intents=[], decision="UNKNOWN", unknown=True),
            _case("113", "unknown", "宇宙的尽头在哪里", problem_types=["UNKNOWN"], intents=[], decision="UNKNOWN", unknown=True),
            _case("114", "unknown", "帮我写首诗", problem_types=["UNKNOWN"], intents=[], decision="UNKNOWN", unknown=True),
            _case("115", "unknown", "随机来点什么", problem_types=["UNKNOWN"], intents=[], decision="UNKNOWN", unknown=True),
            _case("116", "unknown", "abcxyz", problem_types=["UNKNOWN"], intents=[], decision="UNKNOWN", unknown=True),
        ]
    )
    rows.extend(
        [
            _case("117", "high_risk_write", "直接执行采购并入库", problem_types=["ACTION"], intents=["procurement.create_draft"], decision="INSUFFICIENT", clarify=True),
            _case("118", "high_risk_write", "自动审批并创建采购单", problem_types=["ACTION"], intents=["procurement.create_draft"], decision="INSUFFICIENT", clarify=True),
            _case("119", "high_risk_write", "把那个涨点价然后立刻生效", problem_types=["ACTION"], intents=["product.price_change"], decision="INSUFFICIENT", clarify=True),
            _case("120", "skill_conflict", "查询昨天的销售额", problem_types=["QUERY"], intents=["sales.summary"], decision="CLEAR", skills=[]),
            _case("121", "skill_conflict", "查一下库存", problem_types=["QUERY"], intents=["inventory.query"], decision="CLEAR", skills=[]),
            _case("122", "skill_conflict", "查询库存并制定补货计划", problem_types=["QUERY", "ANALYZE"], intents=["inventory.query", "procurement.replenishment_plan"], decision="CLEAR", mode="multi", multi=True, skills=[]),
            _case("123", "skill_conflict", "分析一下", problem_types=["ANALYZE"], intents=["inventory.coverage_analysis"], decision="INSUFFICIENT", clarify=True, skills=[]),
            _case("124", "high_risk_write", "删除所有订单", problem_types=["ACTION"], intents=["sales.order_cancel"], decision="CLEAR"),
            _case("125", "high_risk_write", "我只是问问，不要真的创建采购单", problem_types=["GUIDE"], intents=["procurement.how_to"], decision="CLEAR"),
        ]
    )
    rows.extend([
        _case("126", "sales_rank", "哪个销售订单金额最大？", problem_types=["QUERY"], intents=["sales.order_query"], decision="CLEAR", query_shapes=["RANK"]),
        _case("127", "sales_rank", "查询 ERP 数据 销售订单 哪个订单金额最大", problem_types=["QUERY"], intents=["sales.order_query"], decision="CLEAR", query_shapes=["RANK"]),
        _case("128", "sales_rank", "哪个订单金额最小？", problem_types=["QUERY"], intents=["sales.order_query"], decision="CLEAR", query_shapes=["RANK"]),
        _case("129", "sales_rank", "金额最高的十笔销售订单", problem_types=["QUERY"], intents=["sales.order_query"], decision="CLEAR", query_shapes=["RANK"]),
        _case("130", "sales_aggregate", "最近七天销售订单总金额", problem_types=["QUERY"], intents=["sales.order_query"], decision="CLEAR", query_shapes=["AGGREGATE"]),
        _case("131", "customer_rank", "哪个客户累计采购金额最高？", problem_types=["QUERY"], intents=["sales.summary"], decision="CLEAR", query_shapes=["RANK"]),
        _case("132", "sales_trend", "最近六个月销售趋势", problem_types=["QUERY"], intents=["sales.summary"], decision="CLEAR", query_shapes=["TREND"]),
    ])
    return rows
