from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from app.agents.registry import AgentRegistry, AgentSpec, build_agent_registry
from app.agents.router import AgentRouter
from app.agents.schemas import AgentResult
from app.ai.types import ChatDelta, ModelMessage, ModelToolCall, ModelToolDefinition
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.erp.client import ErpApiClient
from app.graph.multi_agent import MultiAgentWorkflow
from app.graph.workflow import AgentRuntime
from app.tools.executor import ToolExecutor, ToolRuntime
from app.tools.registry import build_tool_registry

from conftest import make_context


class DomainAnswerAdapter:
    def __init__(self) -> None:
        self.messages: list[list[ModelMessage]] = []

    async def stream(
        self,
        messages: list[ModelMessage],
        *,
        tools: list[ModelToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ChatDelta]:
        del tools, tool_choice
        self.messages.append(messages)
        system = str(messages[0].get("content") or "")
        if "汇总 Supervisor" in system:
            yield ChatDelta(text="综合结论：当前证据不足，需人工确认。")
        else:
            yield ChatDelta(text="专业分析完成。")
        yield ChatDelta(finished=True, usage={"prompt_tokens": 10, "completion_tokens": 5})


class FailingAdapter:
    async def stream(self, *_args, **_kwargs) -> AsyncIterator[ChatDelta]:
        raise AppError("模型不可用", code=50380, status_code=503)
        yield ChatDelta(finished=True)  # pragma: no cover


def _executor() -> ToolExecutor:
    client = ErpApiClient(
        base_url="https://erp.test",
        connect_timeout=1,
        read_timeout=1,
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    return ToolExecutor(build_tool_registry(), client)


def test_agent_registry_is_closed_and_rejects_duplicates() -> None:
    registry = build_agent_registry()
    assert {item.agent_name for item in registry.all()} == {
        "sales_agent",
        "inventory_agent",
        "procurement_agent",
        "knowledge_agent",
        "supervisor_agent",
    }
    with pytest.raises(AppError):
        registry.get("write_anything_agent")
    duplicate = AgentSpec("same", 1, "x", "x", frozenset(), (), "isolated", 1, 0, 1, 10)
    with pytest.raises(ValueError, match="重复"):
        AgentRegistry([duplicate, duplicate])
    invalid_tool = AgentSpec(
        "invalid", 1, "x", "x", frozenset({"execute_arbitrary_sql"}), (), "isolated", 1, 1, 1, 10
    )
    with pytest.raises(ValueError, match="未注册工具"):
        AgentRegistry([invalid_tool], known_tools={"get_inventory"})


def test_router_keeps_simple_queries_single_and_cross_domain_multi() -> None:
    router = AgentRouter()
    assert router.route("查询 SKU-001 当前库存").mode == "single"
    route = router.route("分析最近30天销售、库存和采购情况")
    assert route.mode == "multi"
    assert {"sales_agent", "inventory_agent", "procurement_agent"}.issubset(route.agents)
    assert router.route("帮我生成采购单").mode == "workflow"


@pytest.mark.asyncio
async def test_agent_tool_whitelist_is_enforced_before_tool_permission() -> None:
    executor = _executor()
    runtime = ToolRuntime(
        tenant=make_context(extra_permissions={PermissionCode.ORDER_READ.value}),
        access_token="secret-user-token",
        erp_audience_authorized=True,
        allowed_tools=frozenset({"get_sales_order"}),
    )
    with pytest.raises(AppError) as captured:
        await executor.execute(
            ModelToolCall(id="x", name="get_inventory", arguments='{"sku_code":"SKU-1"}'),
            runtime,
        )
    assert captured.value.code == 40378


@pytest.mark.asyncio
async def test_multi_agent_emits_trace_and_keeps_secret_out_of_context() -> None:
    adapter = DomainAnswerAdapter()
    workflow = MultiAgentWorkflow(adapter, _executor())
    context = make_context(
        extra_permissions={
            PermissionCode.ORDER_READ.value,
            PermissionCode.INVENTORY_READ.value,
            PermissionCode.PURCHASE_READ.value,
        }
    )
    runtime = AgentRuntime(
        tools=ToolRuntime(
            tenant=context,
            access_token="secret-user-token",
            erp_audience_authorized=True,
            request_id="request-v8",
        ),
        agent_run_id=81,
    )
    events = [
        item
        async for item in workflow.stream(
            [{"role": "user", "content": "分析最近30天销售、库存和采购情况"}],
            context=runtime,
        )
    ]
    assert any(
        item["event"] == "agent_route" and item["data"]["mode"] == "multi" for item in events
    )
    started = {item["data"]["agent_name"] for item in events if item["event"] == "agent_start"}
    assert {"sales_agent", "inventory_agent", "procurement_agent", "supervisor_agent"}.issubset(
        started
    )
    assert all(
        item["data"]["request_id"] == "request-v8"
        for item in events
        if item["event"].startswith("agent_")
    )
    procurement_starts = [
        item
        for item in events
        if item["event"] == "agent_start" and item["data"]["agent_name"] == "procurement_agent"
    ]
    assert len(procurement_starts) == 1
    assert events[-1]["event"] == "done"
    assert "secret-user-token" not in repr(adapter.messages)


@pytest.mark.asyncio
async def test_single_agent_failure_emits_terminal_agent_error() -> None:
    workflow = MultiAgentWorkflow(FailingAdapter(), _executor())
    runtime = AgentRuntime(
        tools=ToolRuntime(
            tenant=make_context(extra_permissions={PermissionCode.INVENTORY_READ.value}),
            access_token="secret-user-token",
            erp_audience_authorized=True,
            request_id="request-v8-failed",
        ),
        agent_run_id=82,
    )
    events: list[dict] = []
    with pytest.raises(AppError):
        async for item in workflow.stream(
            [{"role": "user", "content": "查询 SKU-001 当前库存"}], context=runtime
        ):
            events.append(item)
    assert any(
        item["event"] == "agent_error" and item["data"]["agent_task_id"] == "single-agent-1"
        for item in events
    )


def test_evidence_merge_deduplicates_same_observation_but_not_different_time() -> None:
    base = {
        "source_type": "ERP",
        "resource_type": "get_inventory",
        "resource_id": "SKU-1",
        "observed_at": "2026-10-24T01:00:00+00:00",
    }
    results = [
        AgentResult(
            agent_name="sales_agent",
            task_id="s1",
            status="SUCCEEDED",
            evidences=[base],
            duration_ms=1,
        ),
        AgentResult(
            agent_name="inventory_agent",
            task_id="i1",
            status="SUCCEEDED",
            evidences=[base, base | {"observed_at": "2026-10-24T01:01:00+00:00"}],
            duration_ms=1,
        ),
    ]
    merged = MultiAgentWorkflow._merge_evidence(results)
    assert len(merged) == 2
    assert [item["citation_id"] for item in merged] == ["E1", "E2"]


def test_v8_evaluation_set_has_thirty_deterministic_route_cases() -> None:
    cases = json.loads(
        (Path(__file__).parents[1] / "evals" / "v8_cases.json").read_text(encoding="utf-8")
    )
    assert len(cases) >= 30
    router = AgentRouter()
    assert all(router.route(item["query"]).mode == item["expected_mode"] for item in cases)
