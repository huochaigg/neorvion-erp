"""V15 查询结构与 V14 Skill 能力判断的确定性回归。"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from app.ai.types import ChatDelta, ModelToolCall
from app.core.config import settings
from app.core.exceptions import AppError
from app.erp.client import ErpApiClient
from app.graph.workflow import AgentRuntime, CopilotWorkflow
from app.intent.context import ContextResolver
from app.intent.query import describe_query
from app.intent.service import IntentUnderstandingService
from app.skills.applicability import assess_skill, pending_relation
from app.skills.catalog import SkillCatalogEntry, SkillCatalogSnapshot
from app.skills.chat import prepare_chat_skill
from app.skills.classification import TaskClassifier
from app.skills.selector import SkillSelection, SkillSelector
from app.tools.executor import ToolExecutor, ToolRuntime
from app.tools.registry import ToolRegistry, build_tool_registry
from app.tools.schemas import ListSalesOrdersArgs

from conftest import make_context


@pytest.mark.parametrize("message,shape,metric,direction,limit", [
    ("哪个销售订单金额最大？", "RANK", "total_amount", "DESC", 1),
    ("查询 ERP 数据 销售订单 哪个订单金额最大", "RANK", "total_amount", "DESC", 1),
    ("最贵的一笔订单是哪个？", "RANK", "total_amount", "DESC", 1),
    ("哪个订单金额最小？", "RANK", "total_amount", "ASC", 1),
    ("金额最高的十笔销售订单", "RANK", "total_amount", "DESC", 10),
    ("金额最低的五笔销售订单", "RANK", "total_amount", "ASC", 5),
    ("最近一个月金额最大的订单", "RANK", "total_amount", "DESC", 1),
    ("美元订单金额最高的前五名", "RANK", "total_amount", "DESC", 5),
    ("查询销售订单 SO2026000004", "DETAIL", None, None, None),
    ("最近七天的销售订单列表", "LIST", None, None, None),
    ("最近七天销售订单总金额", "AGGREGATE", "total_amount", None, None),
    ("本月和上月销售额对比", "COMPARE", "total_amount", None, None),
    ("最近六个月销售趋势", "TREND", None, None, None),
    ("哪个客户累计采购金额最高？", "RANK", "total_amount", "DESC", 1),
    ("不要查询订单详情，查销售金额排名", "RANK", "total_amount", "DESC", 10),
])
def test_query_shape_structural(message, shape, metric, direction, limit):
    query = describe_query(message)
    assert (query.shape, query.metric, query.sort_order, query.limit) == (shape, metric, direction, limit)
    assert query.negative is False


@pytest.mark.asyncio
async def test_v15_enabled_has_rank_task_and_disabled_preserves_legacy_route():
    context = ContextResolver().resolve(tenant_id=1, user_id=1, conversation_id=None, current_text="查询 ERP 数据 销售订单 哪个订单金额最大")
    service = IntentUnderstandingService()
    enabled = await service.resolve(context, force_mode="ENABLED", skill_mode="AUTO")
    assert enabled.decision == "CLEAR"
    assert enabled.tasks[0].query_shape == "RANK"
    assert enabled.tasks[0].metric == "total_amount"
    assert enabled.tasks[0].limit == 1
    assert enabled.tasks[0].missing_slots == ()
    assert enabled.routing_plan.skill_policy == "SKIP"
    disabled = await service.resolve(context, force_mode="DISABLED")
    assert disabled.applied is False and disabled.tasks == ()
    shadow = await service.resolve(context, force_mode="SHADOW")
    assert shadow.applied is False and shadow.tasks[0].query_shape == "RANK"


@pytest.mark.asyncio
async def test_v15_multiturn_rank_modification_keeps_original_entity_and_metric():
    history = [{"role": "user", "content": "哪个销售订单金额最大？"}, {"role": "assistant", "content": "已完成查询"}]
    for phrase, limit, order in (("改为前十笔", 10, "DESC"), ("改为金额最小", 1, "ASC")):
        context = ContextResolver().resolve(tenant_id=1, user_id=1, conversation_id=3, current_text=phrase, recent_messages=history)
        result = await IntentUnderstandingService().resolve(context, force_mode="ENABLED")
        assert result.decision == "CLEAR"
        assert result.tasks[0].query_shape == "RANK"
        assert result.tasks[0].entity == "sales_order"
        assert result.tasks[0].metric == "total_amount"
        assert result.tasks[0].limit == limit and result.tasks[0].sort_order == order


def test_skill_retrieval_never_implies_applicability_or_pending():
    question = "查询 ERP 数据 销售订单 哪个订单金额最大"
    applicable, reason = assess_skill(question, ["get_sales_order"])
    assert applicable is False and "排名" in reason
    assert assess_skill(question, ["list_sales_orders"])[0] is True
    assert assess_skill(question, ["get_sales_order", "list_sales_orders"],
                        input_schema={"required": ["order_id"]})[0] is False
    assert assess_skill("查询销售订单 SO2026000004", ["get_sales_order"],
                        skill_key="sales-order-review")[0] is False
    assert assess_skill("帮我审查一笔销售订单", ["get_sales_order"],
                        input_schema={"required": ["order_id"]}, skill_key="sales-order-review")[0] is True
    assert assess_skill("哪个客户累计采购金额最高？", ["list_sales_orders"])[0] is False
    assert pending_relation(question, missing_fields=["order_id"], skill_key="sales-order-review") == "NEW_TASK"
    assert pending_relation("SO2026000004", missing_fields=["order_id"], skill_key="sales-order-review") == "SUPPLEMENT"
    assert pending_relation("123", missing_fields=["order_id"], skill_key="sales-order-review") == "SUPPLEMENT"
    assert pending_relation("取消刚才的订单查询", missing_fields=["order_id"], skill_key="sales-order-review") == "CANCEL"
    assert describe_query("我不想查询金额最大的订单").negative is True
    assert describe_query("我不想删除订单").negative is False


def test_sort_schema_rejects_arbitrary_sql_and_tenant_scope():
    assert ListSalesOrdersArgs(sort_by="total_amount", sort_order="asc", currency_code="USD", page_size=10).sort_order == "asc"
    with pytest.raises(ValueError):
        ListSalesOrdersArgs(sort_by="created_at; DROP TABLE sales_orders")
    with pytest.raises(ValueError):
        ListSalesOrdersArgs(tenant_id=77)


def test_sales_agent_allows_report_only_identity_but_each_tool_still_checks_its_permission():
    from app.agents.registry import build_agent_registry
    from app.tools.registry import build_tool_registry

    agent = build_agent_registry().get("sales_agent")
    assert agent.can_run(frozenset({"analytics:sales:read"}))
    assert not agent.can_run(frozenset({"copilot:use"}))
    visible = build_tool_registry().definitions(frozenset({"analytics:sales:read"}))
    names = {item["function"]["name"] for item in visible}
    assert "get_sales_summary" in names and "list_sales_orders" not in names


def test_rank_answer_cannot_claim_global_max_from_unsorted_page():
    from app.graph.workflow import CopilotWorkflow

    question = "哪个销售订单金额最大？"
    partial = [{"resource_type": "list_sales_orders", "metadata": {"total": 100, "returned": 20, "page": 1, "sort_by": "created_at", "sort_order": "desc", "truncated": False}}]
    assert "无法确认全局排名" in CopilotWorkflow._guard_global_rank("SO1 最大", partial, question)
    ranked = [{"citation_id": "E1", "resource_type": "list_sales_orders", "metadata": {"total": 100, "returned": 10, "page": 1, "sort_by": "total_amount", "sort_order": "desc", "truncated": False}}]
    assert CopilotWorkflow._guard_global_rank("SO1 最大 [E1]", ranked, question) == "SO1 最大 [E1]"
    assert "缺少可验证" in CopilotWorkflow._guard_global_rank("SO1 最大", ranked, question)
    ranked[0]["metadata"]["truncated"] = True
    assert "无法确认全局排名" in CopilotWorkflow._guard_global_rank("SO1 最大", ranked, question)
    assert "指定币种" in CopilotWorkflow._guard_global_rank("不确定", [], question, tool_events=[{"code": 42272}])


@pytest.mark.asyncio
async def test_auto_falls_back_before_input_collector_but_manual_explains_boundary(monkeypatch):
    """模拟真实 Selector 误召回，验证适用性关卡位于创建 Pending 前。"""
    entry = SkillCatalogEntry(1, 19, "sales-order-review", "销售订单审查", "审查订单", 2, {})

    async def snapshot(self):
        return SimpleNamespace(entries=(entry,), query_latency_ms=0, scanned_count=1, filtered_reasons={})

    async def selected(self, task, catalog, **kwargs):
        return SkillSelection((entry,), "EXPLICIT" if kwargs.get("explicit_skill_key") else "LEXICAL", "词项召回", .9, TaskClassifier().classify(task))

    async def loaded(self, candidate, task):
        return SimpleNamespace(version=SimpleNamespace(allowed_tools=["get_sales_order"]))

    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    monkeypatch.setattr("app.skills.chat.SkillCatalog.snapshot", snapshot)
    monkeypatch.setattr(SkillSelector, "select", selected)
    monkeypatch.setattr("app.skills.chat.SkillRuntimeLoader.load", loaded)
    question = "查询 ERP 数据 销售订单 哪个订单金额最大"
    kwargs = dict(conversation_id=None, message_id=None)
    automatic = await prepare_chat_skill(SimpleNamespace(), make_context(), question, "r-auto", AgentRuntime(), skill_mode="AUTO", **kwargs)
    assert automatic is None
    with pytest.raises(AppError, match="不适用"):
        await prepare_chat_skill(SimpleNamespace(), make_context(), question, "r-manual", AgentRuntime(), skill_mode="MANUAL", explicit_skill_key=entry.skill_key, **kwargs)
    ordinary = await prepare_chat_skill(SimpleNamespace(), make_context(), question, "r-none", AgentRuntime(), skill_mode="NONE", **kwargs)
    assert ordinary is None


@pytest.mark.asyncio
async def test_missing_rank_tool_reports_capability_instead_of_order_id(monkeypatch):
    from app.api.v1.chat import _prepare_with_intent
    from app.intent.integration import IntentClarification

    async def disabled(*args, **kwargs):
        return await IntentUnderstandingService().resolve(
            ContextResolver().resolve(tenant_id=7, user_id=33, conversation_id=None, current_text=kwargs["text"]),
            force_mode="DISABLED",
        )

    async def no_skill(*args, **kwargs):
        return None

    monkeypatch.setattr("app.api.v1.chat.resolve_chat_intent", disabled)
    monkeypatch.setattr("app.api.v1.chat.prepare_chat_skill", no_skill)
    monkeypatch.setattr("app.tools.registry.build_tool_registry", lambda: ToolRegistry([]))
    user = make_context(extra_permissions={"order:read"})
    runtime = AgentRuntime(tools=ToolRuntime(tenant=user, access_token="token", erp_audience_authorized=True))
    response, _ = await _prepare_with_intent(
        SimpleNamespace(), user, "哪个销售订单金额最大？", "capability-test", runtime,
        conversation_id=None, message_id=None, skill_mode="AUTO", explicit_skill_key=None,
        selector_adapter=None, recent_messages=[],
    )
    assert isinstance(response, IntentClarification)
    assert response.public_data["status"] == "CAPABILITY_UNAVAILABLE"
    assert "订单主键" not in response.answer


@pytest.mark.asyncio
async def test_v15_existing_evaluation_runner_replays_query_shape_cases():
    from app.evaluation.metrics import evaluate_case
    from app.intent.evaluation import run_intent_case
    from app.intent.evaluation_catalog import v15_intent_cases

    rows = [case for case in v15_intent_cases() if int(case["external_key"].rsplit("-", 1)[1]) >= 126]
    assert len(rows) == 7
    for case in rows:
        result = await run_intent_case(case)
        _, metrics, assertions = evaluate_case(case, result)
        assert metrics["intent_accuracy"] is True, (case["external_key"], result)
        assert all(item["passed"] for item in assertions if item["kind"] in {"query_shape", "intent_decision", "problem_type"}), (case["external_key"], assertions)


@pytest.mark.asyncio
async def test_v15_full_deterministic_replay_preserves_existing_cases():
    from app.evaluation.metrics import evaluate_case
    from app.intent.evaluation import run_intent_case
    from app.intent.evaluation_catalog import v15_intent_cases

    cases = v15_intent_cases()
    failures = []
    for case in cases:
        _, _, assertions = evaluate_case(case, await run_intent_case(case))
        missed = [item["kind"] for item in assertions if not item["passed"] and item["kind"] in {"intent_selection", "problem_type", "intent_decision", "query_shape"}]
        if missed:
            failures.append((case["external_key"], missed))
    assert len(cases) == 132
    assert not failures, failures


@pytest.mark.asyncio
async def test_pending_business_order_number_uses_authorized_lookup_not_numeric_suffix(monkeypatch):
    import httpx
    from app.erp.client import ErpApiClient
    from app.skills.pending import PendingSkillPrompt, PendingSkillService

    def handler(request):
        assert request.url.params["order_no_exact"] == "SO2026000004"
        assert request.headers["X-Tenant-ID"] == "7"
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"id": 123, "order_no": "SO2026000004"}], "total": 1, "page": 1, "page_size": 2, "has_more": False}})

    erp = ErpApiClient(base_url="https://erp.test", connect_timeout=1, read_timeout=1, transport=httpx.MockTransport(handler))
    async def needs(self, conversation_id, request_id):
        return True

    async def resume(self, conversation_id, task, request_id, *, verified_order_id=None):
        assert verified_order_id == 123
        return PendingSkillPrompt("继续执行", {"status": "READY"})

    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    monkeypatch.setattr("app.skills.chat.get_erp_client", lambda: erp)
    monkeypatch.setattr(PendingSkillService, "needs_order_id", needs)
    monkeypatch.setattr(PendingSkillService, "resume", resume)
    user = make_context(extra_permissions={"order:read"})
    run = AgentRuntime(tools=ToolRuntime(tenant=user, access_token="token", erp_audience_authorized=True))
    result = await prepare_chat_skill(SimpleNamespace(), user, "SO2026000004", "lookup", run, conversation_id=11, message_id=12, skill_mode="AUTO")
    assert isinstance(result, PendingSkillPrompt)
    assert [item["event"] for item in run.preflight_events] == ["tool_start", "tool_end", "evidence"]
    assert run.tools.evidences[0]["citation_id"] == "E1"
    await erp.aclose()


@pytest.mark.asyncio
async def test_restored_pending_checks_pinned_skill_before_collecting_input(monkeypatch):
    """即使关系判断误判为继续，也不能让旧订单审查版本为排名任务收集主键。"""
    from app.skills.pending import PendingSkillService

    row = SimpleNamespace(
        id=41, skill_id=3, skill_version_id=19, missing_fields=["order_id"], selection_snapshot={"selected_skill_keys": ["sales-order-review"]},
        last_client_request_id="previous", expires_at=datetime.now(UTC) + timedelta(minutes=10),
        plan_snapshot={}, status="COLLECTING_INPUT", collected_input={}, clarification="请补充销售订单主键",
    )
    skill = SimpleNamespace(id=3, skill_key="sales-order-review", name="销售订单审查", description="订单详情")
    version = SimpleNamespace(
        id=19, version=2, allowed_tools=["get_sales_order"], allowed_agents=["sales_agent"],
        source_metadata={}, required_permissions=["order:read"],
        input_schema={"type": "object", "properties": {"order_id": {"type": "integer"}}, "required": ["order_id"]},
    )

    class Session:
        async def scalar(self, _statement):
            return row

        async def execute(self, _statement):
            return SimpleNamespace(first=lambda: (skill, version))

        async def commit(self):
            pass

    def never_collect(*_args, **_kwargs):
        raise AssertionError("排名任务进入了订单主键参数收集")

    monkeypatch.setattr("app.skills.pending.pending_relation", lambda *_args, **_kwargs: "CONTINUE")
    monkeypatch.setattr("app.skills.pending.SkillInputCollector.collect", never_collect)
    service = PendingSkillService(Session(), make_context(extra_permissions={"order:read"}))
    result = await service.resume(12, "查询 ERP 数据 销售订单 哪个订单金额最大", "new-request")
    assert result is None
    assert row.status == "CANCELLED"
    assert row.last_client_request_id == "new-request"


@pytest.mark.asyncio
@pytest.mark.parametrize("reply,expected_status", [("123", "READY"), ("取消", "CANCELLED")])
async def test_pending_real_supplement_and_cancel_paths(reply, expected_status):
    from app.skills.pending import PendingSkillPrompt, PendingSkillService, ResumedSkillInput

    row = SimpleNamespace(
        id=41, skill_id=3, skill_version_id=19, missing_fields=["order_id"],
        selection_snapshot={"selected_skill_keys": ["sales-order-review"]},
        last_client_request_id="previous", expires_at=datetime.now(UTC) + timedelta(minutes=10),
        plan_snapshot={}, status="COLLECTING_INPUT", collected_input={}, clarification="请补充订单主键",
    )
    skill = SimpleNamespace(id=3, skill_key="sales-order-review", name="销售订单审查", description="订单详情")
    version = SimpleNamespace(
        id=19, version=2, allowed_tools=["get_sales_order"], allowed_agents=["sales_agent"],
        source_metadata={}, required_permissions=["order:read"],
        input_schema={"type": "object", "properties": {"order_id": {"type": "integer", "minimum": 1}},
                      "required": ["order_id"]},
    )

    class Session:
        async def scalar(self, _statement):
            return row

        async def execute(self, _statement):
            return SimpleNamespace(first=lambda: (skill, version))

        async def commit(self):
            pass

    result = await PendingSkillService(Session(), make_context(extra_permissions={"order:read"})).resume(
        12, reply, "next-request",
    )
    assert row.status == expected_status
    if reply == "123":
        assert isinstance(result, ResumedSkillInput) and result.values["order_id"] == 123
    else:
        assert isinstance(result, PendingSkillPrompt)


@pytest.mark.asyncio
@pytest.mark.parametrize("message,blocks", [
    ("查询 ERP 数据 销售订单 哪个订单金额最大", False),
    ("帮我审查一笔销售订单", False),
    ("1", True),
    ("继续", True),
    ("刚才那个", True),
])
async def test_expired_pending_does_not_end_a_complete_new_request(message, blocks):
    from app.skills.pending import PendingSkillPrompt, PendingSkillService

    row = SimpleNamespace(
        id=41, skill_version_id=19, status="COLLECTING_INPUT", missing_fields=["order_id"],
        selection_snapshot={"selected_skill_keys": ["sales-order-review"]},
        last_client_request_id="old-request", clarification="请补充订单主键",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    class Session:
        async def scalar(self, _statement):
            return row

        async def commit(self):
            pass

    result = await PendingSkillService(Session(), make_context()).resume(12, message, "new-request")
    assert row.status == "EXPIRED"
    assert row.last_client_request_id == "new-request"
    assert isinstance(result, PendingSkillPrompt) is blocks


class _RankAnswerAdapter:
    def __init__(self):
        self.calls = 0

    async def stream(self, messages, *, tools=None, tool_choice=None):
        self.calls += 1
        if not any(item["role"] == "tool" for item in messages):
            yield ChatDelta(finished=True, tool_calls=(ModelToolCall(
                id="rank-1", name="list_sales_orders",
                arguments='{"sort_by":"total_amount","sort_order":"desc","page_size":1,"currency_code":"CNY"}',
            ),))
            return
        yield ChatDelta(text="SO2026000001 金额最大 [E1]")
        yield ChatDelta(finished=True)


@pytest.mark.parametrize("intent_mode", ["DISABLED", "ENABLED"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("skill_mode", ["AUTO", "NONE"])
def test_auto_chat_entry_rejects_wrong_skill_and_executes_rank_tool(
    client, authorize, use_workflow, monkeypatch, intent_mode, stream, skill_mode,
):
    """经真实 HTTP Chat/SSE 入口验证 AUTO 回退；模型、Skill 库与 ERP 使用受控替身。"""
    from app.skills.selector import SkillCandidate

    question = "查询 ERP 数据 销售订单 哪个订单金额最大"
    entry = SkillCatalogEntry(3, 19, "sales-order-review", "销售订单审查", "审查销售订单", 2, {})
    selection_log = []
    tool_log = []

    async def snapshot(self):
        return SkillCatalogSnapshot((entry,), 0, 1, {})

    async def selected(self, task, catalog, **kwargs):
        selection_log.append((task, kwargs.get("explicit_skill_key")))
        return SkillSelection((entry,), "LEXICAL", "销售订单文本相关", .95,
                              TaskClassifier().classify(task), (SkillCandidate(entry.skill_key, .95, ("销售订单",)),))

    async def loaded(self, candidate, task):
        return SimpleNamespace(version=SimpleNamespace(
            allowed_tools=["get_sales_order"], allowed_agents=["sales_agent"],
            input_schema={"type": "object", "properties": {"order_id": {"type": "integer"}}, "required": ["order_id"]},
        ))

    def handler(request):
        tool_log.append((request.headers["X-Tenant-ID"], dict(request.url.params)))
        return httpx.Response(200, json={"code": 0, "data": {
            "items": [{"id": 1, "order_no": "SO2026000001", "total_amount": "32996.00", "currency_code": "CNY"}],
            "total": 1, "page": 1, "page_size": 1, "has_more": False,
            "sort_by": "total_amount", "sort_order": "desc",
        }})

    erp = ErpApiClient(base_url="https://erp.test", connect_timeout=1, read_timeout=1,
                       transport=httpx.MockTransport(handler))
    adapter = _RankAnswerAdapter()
    authorize(extra_permissions={"order:read", "copilot:skill:run"})
    use_workflow(CopilotWorkflow(adapter, ToolExecutor(build_tool_registry(), erp)))
    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    monkeypatch.setattr(settings, "skill_selector_mode", "HYBRID")
    monkeypatch.setattr(settings, "intent_v15_mode", intent_mode)
    monkeypatch.setattr("app.skills.chat.SkillCatalog.snapshot", snapshot)
    monkeypatch.setattr(SkillSelector, "select", selected)
    monkeypatch.setattr("app.skills.chat.SkillRuntimeLoader.load", loaded)

    path = "/api/v1/chat/stream" if stream else "/api/v1/chat"
    response = client.post(path, json={"messages": [{"role": "user", "content": question}], "skill_mode": skill_mode})
    assert response.status_code == 200, response.text
    if stream:
        assert "event: skill_input_required" not in response.text
        assert "event: tool_start" in response.text and "event: tool_end" in response.text
        assert "SO2026000001 金额最大 [E1]" in response.text
    else:
        assert response.json()["data"]["answer"] == "SO2026000001 金额最大 [E1]"
        assert response.json()["data"]["skill"] is None
    assert selection_log == ([(question, None)] if skill_mode == "AUTO" else [])
    assert len(tool_log) == 1
    assert tool_log[0][0] == "7"
    assert tool_log[0][1]["sort_by"] == "total_amount"
    assert adapter.calls == 2
    asyncio.run(erp.aclose())


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("pending_status", ["NONE", "ACTIVE", "EXPIRED"])
def test_existing_pending_auto_chat_entry_switches_to_rank(
    client, authorize, use_workflow, monkeypatch, stream, pending_status,
):
    """新旧会话的 Chat/SSE 请求走真实入口及恢复判断；持久层、模型与 ERP 为替身。"""
    from app.api.deps import get_db
    from app.main import app
    from app.services.persistent_chat import PersistentTurn

    question = "查询 ERP 数据 销售订单 哪个订单金额最大"
    row = SimpleNamespace(
        id=41, skill_id=3, skill_version_id=19, status="COLLECTING_INPUT",
        missing_fields=["order_id"], collected_input={},
        selection_snapshot={"selected_skill_keys": ["sales-order-review"]}, plan_snapshot={},
        last_client_request_id="old-request", clarification="请补充销售订单主键",
        expires_at=datetime.now(UTC) + timedelta(minutes=-1 if pending_status == "EXPIRED" else 10),
    )

    class Session:
        async def scalar(self, _statement):
            return row if pending_status != "NONE" and row.status == "COLLECTING_INPUT" else None

        async def commit(self):
            pass

    async def db_override():
        yield Session()

    async def prepare(self, conversation_id, content, client_request_id, request_id):
        return PersistentTurn(conversation_id, 90, request_id, [{"role": "user", "content": content}])

    async def events(self, turn, runtime, disconnected, skill_session=None):
        assert skill_session is None
        async for event in self.workflow.stream(turn.history, context=runtime):
            yield event

    async def selected(self, task, catalog, **kwargs):
        return SkillSelection((catalog[0],), "LEXICAL", "订单文本相关", .9, TaskClassifier().classify(task))

    async def snapshot(self):
        return SkillCatalogSnapshot((SkillCatalogEntry(
            3, 19, "sales-order-review", "销售订单审查", "审查销售订单", 2, {},
        ),), 0, 1, {})

    async def loaded(self, candidate, task):
        return SimpleNamespace(version=SimpleNamespace(
            allowed_tools=["get_sales_order"], allowed_agents=["sales_agent"],
        ))

    tool_calls = []

    def handler(request):
        tool_calls.append(request.url.params["sort_by"])
        return httpx.Response(200, json={"code": 0, "data": {
            "items": [{"id": 1, "order_no": "SO2026000001", "total_amount": "32996", "currency_code": "CNY"}],
            "total": 1, "page": 1, "page_size": 1, "has_more": False,
            "sort_by": "total_amount", "sort_order": "desc",
        }})

    erp = ErpApiClient(base_url="https://erp.test", connect_timeout=1, read_timeout=1,
                       transport=httpx.MockTransport(handler))
    adapter = _RankAnswerAdapter()
    authorize(extra_permissions={"order:read", "copilot:skill:run"})
    use_workflow(CopilotWorkflow(adapter, ToolExecutor(build_tool_registry(), erp)))
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    monkeypatch.setattr(settings, "intent_v15_mode", "DISABLED")
    monkeypatch.setattr("app.services.persistent_chat.PersistentChatService.prepare", prepare)
    monkeypatch.setattr("app.services.persistent_chat.PersistentChatService.events", events)
    monkeypatch.setattr("app.skills.chat.SkillCatalog.snapshot", snapshot)
    monkeypatch.setattr(SkillSelector, "select", selected)
    monkeypatch.setattr("app.skills.chat.SkillRuntimeLoader.load", loaded)
    path = "/api/v1/conversations/12/messages" if stream else "/api/v1/chat"
    repeats = 2 if pending_status == "EXPIRED" and stream else 1
    for index in range(repeats):
        response = client.post(path, json={
            "conversation_id": 12, "message": question, "client_request_id": f"new-request-{index}",
            "skill_mode": "AUTO",
        })
        assert response.status_code == 200, response.text
        assert "skill_input_required" not in response.text
        assert "已过期" not in response.text
        assert "请补充销售订单主键" not in response.text
        assert "SO2026000001" in response.text
    expected = {"NONE": "COLLECTING_INPUT", "ACTIVE": "CANCELLED", "EXPIRED": "EXPIRED"}
    assert row.status == expected[pending_status]
    assert tool_calls == ["total_amount"] * repeats
    assert adapter.calls == 2 * repeats
    asyncio.run(erp.aclose())


@pytest.mark.parametrize("stream", [False, True])
def test_actual_review_request_still_collects_order_id_at_chat_entry(
    client, authorize, use_workflow, monkeypatch, stream,
):
    """订单审查任务确实需要主键时，Chat/SSE 才产生参数补全事件。"""
    from app.api.deps import get_db
    from app.main import app
    from app.services.persistent_chat import PersistentTurn
    from app.skills.pending import PendingSkillPrompt

    question = "帮我按照订单审查流程审查一笔销售订单"
    entry = SkillCatalogEntry(3, 19, "sales-order-review", "销售订单审查", "订单审查", 2, {})

    class EmptySession:
        async def scalar(self, _statement):
            return None

    async def db_override():
        yield EmptySession()

    async def prepare(self, conversation_id, content, client_request_id, request_id):
        return PersistentTurn(conversation_id, 90, request_id, [{"role": "user", "content": content}])

    async def complete_without_run(self, turn, answer, runtime=None):
        assert "销售订单主键" in answer

    async def events(self, *args, **kwargs):
        raise AssertionError("缺少真实业务参数时不应运行 Agent Graph")
        yield {}

    async def snapshot(self):
        return SkillCatalogSnapshot((entry,), 0, 1, {})

    async def selected(self, task, catalog, **kwargs):
        return SkillSelection((entry,), "LEXICAL", "订单审查", .9, TaskClassifier().classify(task))

    async def loaded(self, candidate, task):
        return SimpleNamespace(version=SimpleNamespace(
            allowed_tools=["get_sales_order"], allowed_agents=["sales_agent"],
            input_schema={"type": "object", "properties": {
                "order_id": {"type": "integer", "description": "销售订单主键，不是租户 ID 或外部订单号"},
            }, "required": ["order_id"]},
        ))

    async def create(self, conversation_id, entry, values, missing, clarification, request_id, selection_snapshot):
        assert missing == ("order_id",)
        return PendingSkillPrompt(clarification, {"pending_id": 41, "missing_fields": list(missing)})

    authorize(extra_permissions={"order:read", "copilot:skill:run"})
    adapter = _RankAnswerAdapter()
    use_workflow(CopilotWorkflow(adapter))
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    monkeypatch.setattr(settings, "intent_v15_mode", "DISABLED")
    monkeypatch.setattr("app.services.persistent_chat.PersistentChatService.prepare", prepare)
    monkeypatch.setattr("app.services.persistent_chat.PersistentChatService.complete_without_run", complete_without_run)
    monkeypatch.setattr("app.services.persistent_chat.PersistentChatService.events", events)
    monkeypatch.setattr("app.skills.chat.SkillCatalog.snapshot", snapshot)
    monkeypatch.setattr(SkillSelector, "select", selected)
    monkeypatch.setattr("app.skills.chat.SkillRuntimeLoader.load", loaded)
    monkeypatch.setattr("app.skills.chat.PendingSkillService.create", create)
    path = "/api/v1/conversations/12/messages" if stream else "/api/v1/chat"
    response = client.post(path, json={
        "conversation_id": 12, "message": question, "client_request_id": "review-request", "skill_mode": "AUTO",
    })
    assert response.status_code == 200, response.text
    assert "销售订单主键" in response.text
    if stream:
        assert "event: skill_input_required" in response.text
        assert "event: tool_start" not in response.text
    else:
        assert response.json()["data"]["skill"]["missing_fields"] == ["order_id"]
    assert adapter.calls == 0


def test_manual_order_review_rank_request_explains_boundary_at_chat_entry(
    client, authorize, use_workflow, monkeypatch,
):
    entry = SkillCatalogEntry(3, 19, "sales-order-review", "销售订单审查", "审查销售订单", 2, {})

    async def snapshot(self):
        return SkillCatalogSnapshot((entry,), 0, 1, {})

    async def selected(self, task, catalog, **kwargs):
        assert kwargs["explicit_skill_key"] == entry.skill_key
        return SkillSelection((entry,), "EXPLICIT", "用户指定", 1, TaskClassifier().classify(task))

    async def loaded(self, candidate, task):
        return SimpleNamespace(version=SimpleNamespace(
            allowed_tools=["get_sales_order"], allowed_agents=["sales_agent"],
            input_schema={"type": "object", "required": ["order_id"]},
        ))

    authorize(extra_permissions={"order:read", "copilot:skill:run"})
    adapter = _RankAnswerAdapter()
    use_workflow(CopilotWorkflow(adapter))
    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    monkeypatch.setattr(settings, "intent_v15_mode", "DISABLED")
    monkeypatch.setattr("app.skills.chat.SkillCatalog.snapshot", snapshot)
    monkeypatch.setattr(SkillSelector, "select", selected)
    monkeypatch.setattr("app.skills.chat.SkillRuntimeLoader.load", loaded)
    response = client.post("/api/v1/chat", json={
        "messages": [{"role": "user", "content": "查询 ERP 数据 销售订单 哪个订单金额最大"}],
        "skill_mode": "MANUAL", "skill_key": "sales-order-review",
    })
    assert response.status_code == 422
    assert response.json()["code"] == 42298
    assert "不适用" in response.json()["message"]
    assert adapter.calls == 0
