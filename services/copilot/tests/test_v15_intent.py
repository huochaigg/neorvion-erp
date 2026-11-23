from __future__ import annotations

import pytest
from app.intent.context import ContextResolver
from app.intent.evaluation_catalog import v15_intent_cases
from app.intent.registry import IntentRegistry, get_intent_registry
from app.intent.schemas import ConversationContext
from app.intent.service import IntentUnderstandingService


def _context(text: str, messages: list[dict[str, str]] | None = None) -> ConversationContext:
    return ContextResolver().resolve(
        tenant_id=7,
        user_id=11,
        conversation_id=1,
        current_text=text,
        recent_messages=messages,
    )


async def _resolve(text: str, messages: list[dict[str, str]] | None = None):
    return await IntentUnderstandingService().resolve(_context(text, messages), force_mode="ENABLED")


@pytest.mark.asyncio
async def test_registry_rejects_duplicate_and_unknown_mapping():
    from app.intent.schemas import IntentDefinition

    with pytest.raises(ValueError, match="重复"):
        IntentRegistry(
            (
                IntentDefinition(
                    intent_key="general.chat",
                    name="a",
                    description="普通对话用于校验重复键。",
                    domain="GENERAL",
                    problem_type="CHAT",
                ),
                IntentDefinition(
                    intent_key="general.chat",
                    name="b",
                    description="普通对话用于校验重复键。",
                    domain="GENERAL",
                    problem_type="CHAT",
                ),
            )
        )
    with pytest.raises(ValueError, match="未注册 Agent"):
        IntentRegistry(
            (
                IntentDefinition(
                    intent_key="demo.bad",
                    name="bad",
                    description="错误映射未注册 Agent。",
                    domain="GENERAL",
                    problem_type="QUERY",
                    candidate_agents=("ghost_agent",),
                ),
            )
        )
    assert "inventory.query" in get_intent_registry().keys()
    assert get_intent_registry().require("procurement.create_draft").executable


@pytest.mark.asyncio
async def test_focus_cases_problem_type_intent_and_safety():
    cases = [
        ("查一下库存", "QUERY", "inventory.query", "CLEAR", False),
        ("货还够不够？", "QUERY", "inventory.query", "CLEAR", False),
        ("我不想删除订单", "GUIDE", "knowledge.how_to", "CLEAR", False),
        ("删除订单怎么操作？", "GUIDE", "knowledge.how_to", "CLEAR", False),
        ("最近生意怎么样？", "ANALYZE", "sales.analysis", "CLEAR", False),
        ("查询昨天的销售额", "QUERY", "sales.summary", "CLEAR", False),
        ("帮我创建采购单", "ACTION", "procurement.create_draft", "INSUFFICIENT", False),
        ("我只是问问，不要真的创建采购单", "GUIDE", "procurement.how_to", "CLEAR", False),
        ("帮我查询 SKU-001 的库存", "QUERY", "inventory.query", "CLEAR", False),
        ("这个多少钱？", "QUERY", "product.price_query", "INSUFFICIENT", False),
        ("把那个涨点价", "ACTION", "product.price_change", "INSUFFICIENT", False),
        ("你好", "CHAT", "general.chat", "CLEAR", False),
        ("查询张三", "QUERY", "party.lookup", "AMBIGUOUS", False),
        ("最近有什么商品比较畅销？", "QUERY", "sales.hot_selling", "CLEAR", False),
        ("我不是要创建采购单，只是想了解流程", "GUIDE", "procurement.how_to", "CLEAR", False),
        ("查询最近七天的销售情况", "QUERY", "sales.summary", "CLEAR", False),
        ("分析一下刚才查询的 SKU-001", "ANALYZE", "inventory.coverage_analysis", "CLEAR", False),
    ]
    for text, problem, intent, decision, allow_write in cases:
        result = await _resolve(text)
        assert problem in result.problem_types, text
        assert intent in result.resolved_intents, (text, result.resolved_intents)
        assert result.decision == decision, (text, result.decision, result.fallback_reason)
        assert result.tool_policy.allow_propose_action is allow_write, text
        assert "propose_action" in result.tool_policy.blocked_tools or allow_write


@pytest.mark.asyncio
async def test_multi_intent_keeps_both_tasks_and_skips_single_skill():
    result = await _resolve("查询库存并制定补货计划")
    assert result.resolved_intents == ("inventory.query", "procurement.replenishment_plan")
    assert result.routing_plan.skill_policy == "SKIP"
    assert result.routing_plan.agent_mode == "multi"
    assert result.routing_plan.allow_multi_agent is True


@pytest.mark.asyncio
async def test_create_then_query_does_not_drop_second_task():
    result = await _resolve("帮我创建采购单，再查询库存")
    assert "procurement.create_draft" in result.resolved_intents
    assert "inventory.query" in result.resolved_intents
    assert len(result.tasks) == 2


@pytest.mark.asyncio
async def test_analyze_without_context_asks_instead_of_forcing_skill():
    result = await _resolve("分析一下")
    assert result.decision == "INSUFFICIENT"
    assert result.routing_plan.clarify is True
    assert result.routing_plan.skill_policy == "SKIP"
    assert result.tool_policy.allow_propose_action is False


@pytest.mark.asyncio
async def test_analyze_with_trusted_sku_context():
    result = await _resolve("分析一下", [{"role": "user", "content": "查询 SKU-001 的库存"}])
    assert "inventory.coverage_analysis" in result.resolved_intents
    assert result.tasks[0].slots.get("sku_code", "").upper().startswith("SKU")
    assert result.decision == "CLEAR"


@pytest.mark.asyncio
async def test_unconfirmed_do_it_does_not_enable_write_tools():
    result = await _resolve("那就按刚才说的办")
    assert result.tool_policy.allow_propose_action is False
    assert result.decision != "UNKNOWN" or result.resolved_intents


@pytest.mark.asyncio
async def test_disabled_flag_does_not_apply_routing():
    result = await IntentUnderstandingService().resolve(_context("查一下库存"), force_mode="DISABLED")
    assert result.applied is False
    assert result.classifier_method == "DISABLED"


@pytest.mark.asyncio
async def test_query_inventory_does_not_select_analysis_skill():
    result = await _resolve("查一下库存")
    assert result.routing_plan.skill_keys == ()
    assert "inventory-analysis" in result.routing_plan.forbid_skill_keys


@pytest.mark.asyncio
async def test_sales_summary_does_not_select_order_review_skill():
    result = await _resolve("查询昨天的销售额")
    assert "sales-order-review" not in result.routing_plan.skill_keys
    assert result.resolved_intents == ("sales.summary",)


@pytest.mark.asyncio
async def test_evaluation_catalog_is_hand_authored_and_large_enough():
    rows = v15_intent_cases()
    assert len(rows) >= 100
    keys = [item["external_key"] for item in rows]
    assert len(keys) == len(set(keys))
    assert any(item["case_type"] == "negation" for item in rows)
    assert any(item["case_type"] == "multi_intent" for item in rows)
    assert all(item["expected_behavior"]["expected_intent_keys"] is not None for item in rows)


@pytest.mark.asyncio
async def test_intent_replay_runner_scores_focus_query():
    from app.evaluation.metrics import evaluate_case
    from app.intent.evaluation import run_intent_case
    from app.intent.evaluation_catalog import v15_intent_cases

    case = next(item for item in v15_intent_cases() if item["external_key"] == "v15-intent-001")
    result = await run_intent_case(case)
    outcome, metrics, assertions = evaluate_case(case, result)
    assert metrics["intent_accuracy"] is True
    assert any(item["kind"] == "intent_selection" and item["passed"] for item in assertions)
    assert outcome in {"TASK_SUCCESS", "TASK_FAILED"}


@pytest.mark.asyncio
async def test_tool_executor_blocks_propose_action_when_intent_forbids_write():
    import httpx
    from app.ai.types import ModelToolCall
    from app.erp.client import ErpApiClient
    from app.tools.executor import ToolExecutor, ToolRuntime
    from app.tools.registry import build_tool_registry

    from conftest import make_context

    executor = ToolExecutor(
        build_tool_registry(),
        ErpApiClient(
            base_url="https://erp.test",
            connect_timeout=1,
            read_timeout=1,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "data": {}})),
        ),
    )
    runtime = ToolRuntime(
        tenant=make_context(),
        access_token="user-token",
        erp_audience_authorized=True,
        conversation_id=1,
        forbid_write_tools=True,
        blocked_tools=frozenset({"propose_action", "validate_action_proposal"}),
    )
    with pytest.raises(Exception) as exc:
        await executor.execute(ModelToolCall(id="1", name="propose_action", arguments="{}"), runtime)
    assert getattr(exc.value, "code", None) == 40379


@pytest.mark.asyncio
async def test_skill_selector_honors_intent_skip_for_plain_query():
    from app.skills.catalog import SkillCatalogEntry
    from app.skills.selector import SkillSelector

    result = await _resolve("查一下库存")
    catalog = [
        SkillCatalogEntry(
            1,
            1,
            "inventory-analysis",
            "库存风险分析",
            "覆盖天数",
            1,
            {},
        )
    ]
    selection = await SkillSelector().select("查一下库存", catalog, routing_plan=result.routing_plan)
    assert selection.selected_skills == ()
    assert selection.method == "NO_SKILL"
