"""inventory-analysis 可执行 walkthrough。

默认场景使用专用 PostgreSQL，外部 LLM/ERP 使用确定性替身；Skill API、导入、
审核、启用、SkillExecutionService、LangGraph、ToolExecutor、Evidence 与 SkillRun
均执行真实代码。只有显式提供 COPILOT_V14_LIVE_* 环境变量时才运行真实服务验收。
"""

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import httpx
import pytest
from app.ai.types import ChatDelta, ModelMessage, ModelToolCall, ModelToolDefinition
from app.api.deps import get_db, get_tenant_context, get_workflow
from app.core.config import settings
from app.core.tenant import TenantContext
from app.db.base import Base
from app.db.isolation import REGISTRY
from app.erp.client import ErpApiClient
from app.graph.multi_agent import MultiAgentWorkflow
from app.graph.workflow import AgentRuntime
from app.main import app
from app.mcp.security import validate_arguments
from app.schemas.ecosystem import SkillCreate
from app.services.skill_execution import SkillExecutionService
from app.tools.executor import ToolExecutor, ToolRuntime
from app.tools.registry import build_tool_registry
from fastapi import Request
from neorvion_db import TenantAsyncSession
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


def _postgres_url() -> str:
    url = os.getenv("COPILOT_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("未配置 COPILOT_TEST_DATABASE_URL，跳过 walkthrough PostgreSQL 演示")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("COPILOT_TEST_DATABASE_URL 必须指向名称以 _test 结尾的专用数据库")
    return url


def _context(*, business_permissions: bool = True) -> TenantContext:
    permissions = {
        "copilot:skill:read",
        "copilot:skill:run",
        "copilot:skill:manage",
    }
    if business_permissions:
        permissions.update({"inventory:read", "analytics:sales:read"})
    return TenantContext(
        user_id=14101,
        tenant_id=1410,
        member_id=141001,
        is_owner=False,
        role="ADMIN",
        role_codes=("ADMIN",),
        permission_codes=frozenset(permissions),
        token_jti="v14-walkthrough",
        token_version=1,
        authz_version=1,
    )


class InventorySkillAdapter:
    """只替代外部模型；两轮输出强制走真实 LangGraph Tool 循环。"""

    def __init__(self) -> None:
        self.calls = 0
        self.received_skill_message = ""
        self.received_tool_result = ""

    async def stream(
        self,
        messages: list[ModelMessage],
        *,
        tools: list[ModelToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ChatDelta]:
        del tool_choice
        self.calls += 1
        tool_messages = [item for item in messages if item["role"] == "tool"]
        if not tool_messages:
            self.received_skill_message = str(messages[-1].get("content") or "")
            assert "<untrusted_skill_instructions>" in self.received_skill_message
            assert '"sku_code": "SKU-WALK-001"' in self.received_skill_message
            assert tools is not None
            assert {item["function"]["name"] for item in tools} == {
                "analyze_inventory_coverage"
            }
            yield ChatDelta(
                finished=True,
                tool_calls=(
                    ModelToolCall(
                        id="inventory-coverage-1",
                        name="analyze_inventory_coverage",
                        arguments=(
                            '{"sku_code":"SKU-WALK-001","start_date":"2026-10-01",'
                            '"end_date":"2026-10-31","warehouse_id":12}'
                        ),
                    ),
                ),
                usage={"prompt_tokens": 120, "completion_tokens": 20},
            )
            return
        self.received_tool_result = str(tool_messages[-1].get("content") or "")
        if "工具调用失败" in self.received_tool_result:
            yield ChatDelta(
                text=(
                    '{"summary":"ERP 查询失败，无法完成库存覆盖分析。",'
                    '"coverage_days":0,"evidence_refs":[]}'
                )
            )
            yield ChatDelta(finished=True, usage={"prompt_tokens": 80, "completion_tokens": 20})
            return
        assert "untrusted_erp_tool_result" in self.received_tool_result
        assert '"coverage_days":8.4' in self.received_tool_result
        yield ChatDelta(
            text=(
                '{"summary":"SKU-WALK-001 当前可用库存覆盖约 8.4 天 [E1]；'
                '未提供安全库存和交期，不能给出补货量。",'
                '"coverage_days":8.4,"evidence_refs":["E1"]}'
            )
        )
        yield ChatDelta(
            finished=True,
            usage={"prompt_tokens": 180, "completion_tokens": 60},
        )


def _erp_transport(*, fail: bool = False) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(503, json={"code": 50300, "message": "ERP unavailable"})
        assert request.headers["X-Tenant-ID"] == "1410"
        assert request.headers["Authorization"] == "Bearer walkthrough-user-token"
        if request.url.path == "/api/v1/analytics/sales/sku":
            assert request.url.params["sku_code"] == "SKU-WALK-001"
            assert request.url.params["start_date"] == "2026-10-01"
            assert request.url.params["end_date"] == "2026-10-31"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "sku_id": 101,
                        "sku_code": "SKU-WALK-001",
                        "sku_name": "Walkthrough SKU",
                        "start_date": "2026-10-01",
                        "end_date": "2026-10-31",
                        "period_days": 31,
                        "sales_quantity": 310,
                        "order_count": 20,
                    },
                },
            )
        if request.url.path == "/api/v1/inventory":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "sku_code": "SKU-WALK-001",
                                "warehouse_id": 12,
                                "available_quantity": 84,
                            }
                        ],
                        "total": 1,
                        "page": 1,
                        "page_size": 100,
                    },
                },
            )
        return httpx.Response(404, json={"code": 40400, "message": "unexpected path"})

    return httpx.MockTransport(handler)


def _workflow(*, fail_erp: bool = False) -> tuple[MultiAgentWorkflow, InventorySkillAdapter]:
    adapter = InventorySkillAdapter()
    erp = ErpApiClient(
        base_url="https://erp.walkthrough.test",
        connect_timeout=1,
        read_timeout=1,
        transport=_erp_transport(fail=fail_erp),
    )
    return MultiAgentWorkflow(adapter, ToolExecutor(build_tool_registry(), erp)), adapter


@pytest.mark.asyncio
async def test_inventory_skill_langgraph_tool_evidence_demo() -> None:
    """不需要数据库的快速断点入口：真实 LangGraph + ToolExecutor + Evidence。"""
    workflow, adapter = _workflow()
    template_path = Path(__file__).resolve().parents[1] / "skills" / "inventory-analysis.json"
    template = SkillCreate.model_validate_json(template_path.read_text("utf-8"))
    skill_input = {
        "sku_code": "SKU-WALK-001",
        "start_date": "2026-10-01",
        "end_date": "2026-10-31",
        "warehouse_id": 12,
    }
    runtime = AgentRuntime(
        tools=ToolRuntime(
            tenant=_context(),
            access_token="walkthrough-user-token",
            erp_audience_authorized=True,
            request_id="walkthrough-fast",
            allowed_tools=frozenset(template.version.allowed_tools),
            agent_name="inventory_agent",
        ),
        allow_multi_agent=False,
        agent_name="inventory_agent",
    )
    try:
        answer, usage = await workflow.invoke(
            [
                {
                    "role": "user",
                    "content": SkillExecutionService._message(template.version, skill_input),
                }
            ],
            context=runtime,
        )
        output = SkillExecutionService._parse_output(answer)
        validate_arguments(template.version.output_schema, output)
        assert output["coverage_days"] == 8.4
        assert usage == {"prompt_tokens": 180, "completion_tokens": 60}
        assert runtime.tools is not None
        assert runtime.tools.tool_events[0]["name"] == "analyze_inventory_coverage"
        assert runtime.tools.evidences[0]["source_type"] == "ERP"
        assert adapter.calls == 2
    finally:
        await workflow.executor.client.aclose()


@pytest.mark.asyncio
async def test_inventory_skill_complete_mock_walkthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实内部链路 + Mock LLM/ERP；不是生产环境 E2E 验收。"""
    engine = create_async_engine(_postgres_url())
    monkeypatch.setattr(settings, "quota_enforcement_enabled", False)
    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    context = _context()
    session = TenantAsyncSession(
        context.tenant_id,
        registry=REGISTRY,
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )
    workflow, adapter = _workflow()

    async def override_context(request: Request) -> TenantContext:
        request.state.access_token = "walkthrough-user-token"
        request.state.jwt_audiences = (settings.erp_jwt_audience,)
        return context

    async def override_db():
        yield session

    app.dependency_overrides[get_tenant_context] = override_context
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_workflow] = lambda: workflow
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://copilot.test"
        ) as client:
            skills_root = Path(__file__).resolve().parents[1] / "skills"
            archive_buffer = io.BytesIO()
            with zipfile.ZipFile(archive_buffer, "w") as archive:
                archive.write(
                    skills_root / "inventory-analysis" / "SKILL.md",
                    "inventory-analysis/SKILL.md",
                )
                archive.write(
                    skills_root / "inventory-analysis" / "references" / "inventory-rules.md",
                    "inventory-analysis/references/inventory-rules.md",
                )
                archive.write(
                    skills_root / "inventory-analysis.json",
                    "inventory-analysis/governance.json",
                )
            package_import = await client.post(
                "/api/v1/ecosystem/skills/packages/import",
                files={"archive": ("inventory-analysis.zip", archive_buffer.getvalue(), "application/zip")},
            )
            assert package_import.status_code == 200
            assert package_import.json()["data"]["status"] == "IMPORTED"
            skill_id = package_import.json()["data"]["skill_id"]

            imported = await client.post(
                "/api/v1/ecosystem/skills/templates/import",
                json={"skill_keys": ["inventory-analysis"]},
            )
            assert imported.status_code == 200
            import_result = imported.json()["data"][0]
            assert import_result["status"] == "UNCHANGED"
            assert import_result["skill_id"] == skill_id

            reviewed = await client.post(
                f"/api/v1/ecosystem/skills/{skill_id}/review", json={"approved": True}
            )
            assert reviewed.status_code == 200
            assert reviewed.json()["data"]["enabled"] is False
            enabled = await client.post(
                f"/api/v1/ecosystem/skills/{skill_id}/enabled", json={"approved": True}
            )
            assert enabled.status_code == 200

            run_response = await client.post(
                f"/api/v1/ecosystem/skills/{skill_id}/runs",
                json={
                    "input": {
                        "sku_code": "SKU-WALK-001",
                        "start_date": "2026-10-01",
                        "end_date": "2026-10-31",
                        "warehouse_id": 12,
                    },
                    "agent_name": "inventory_agent",
                    "idempotency_key": "inventory-walkthrough-success",
                },
            )
            assert run_response.status_code == 200
            run = run_response.json()["data"]
            assert run["status"] == "SUCCEEDED"
            assert run["output_snapshot"]["result"]["coverage_days"] == 8.4
            assert run["output_snapshot"]["execution"]["agent_name"] == "inventory_agent"
            assert run["output_snapshot"]["tool_calls"][0]["name"] == (
                "analyze_inventory_coverage"
            )
            evidence = run["output_snapshot"]["evidence"]
            assert evidence[0]["source_type"] == "ERP"
            assert evidence[0]["tool_call_id"]
            assert adapter.calls == 2
            assert "# 库存覆盖分析" in adapter.received_skill_message

            conversation = await client.post("/api/v1/conversations", json={"title": "V14.2 Skill"})
            assert conversation.status_code == 200
            conversation_id = conversation.json()["data"]["id"]
            chat = await client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "client_request_id": "v142-inventory-chat-request",
                    "message": (
                        "分析 SKU-WALK-001 从2026-10-01到2026-10-31 在仓库12的"
                        "库存覆盖天数，并说明库存风险。"
                    ),
                },
            )
            assert chat.status_code == 200
            stream = chat.text
            assert "event: skill_selected" in stream
            assert "event: skill_resource_loaded" in stream
            assert "event: tool_end" in stream
            assert "event: evidence" in stream
            assert "event: skill_done" in stream
            assert "event: done" in stream
            conversation_detail = await client.get(f"/api/v1/conversations/{conversation_id}")
            assert conversation_detail.status_code == 200
            assistant = conversation_detail.json()["data"]["messages"][-1]
            assert assistant["status"] == "COMPLETED"
            assert assistant["skill_runs"][0]["status"] == "SUCCEEDED"
            assert assistant["skill_runs"][0]["skill_key"] == "inventory-analysis"
            assert assistant["skill_runs"][0]["loaded_resources"] == [
                "references/inventory-rules.md"
            ]
            assert assistant["evidences"][0]["source_type"] == "ERP"

            detail = await client.get(
                f"/api/v1/ecosystem/skills/{skill_id}/runs/{run['id']}"
            )
            assert detail.status_code == 200
            assert detail.json()["data"]["status"] == "SUCCEEDED"

            invalid = await client.post(
                f"/api/v1/ecosystem/skills/{skill_id}/runs",
                json={
                    "input": {"sku_code": "SKU-WALK-001"},
                    "idempotency_key": "inventory-walkthrough-invalid",
                },
            )
            assert invalid.status_code == 400

            denied_context = _context(business_permissions=False)

            async def override_denied_context(request: Request) -> TenantContext:
                request.state.access_token = "walkthrough-user-token"
                request.state.jwt_audiences = (settings.erp_jwt_audience,)
                return denied_context

            app.dependency_overrides[get_tenant_context] = override_denied_context
            denied = await client.post(
                f"/api/v1/ecosystem/skills/{skill_id}/runs",
                json={
                    "input": {
                        "sku_code": "SKU-WALK-001",
                        "start_date": "2026-10-01",
                        "end_date": "2026-10-31",
                    },
                    "idempotency_key": "inventory-walkthrough-denied",
                },
            )
            assert denied.status_code == 403

            app.dependency_overrides[get_tenant_context] = override_context
            failing_workflow, _ = _workflow(fail_erp=True)
            app.dependency_overrides[get_workflow] = lambda: failing_workflow
            tool_failed = await client.post(
                f"/api/v1/ecosystem/skills/{skill_id}/runs",
                json={
                    "input": {
                        "sku_code": "SKU-WALK-001",
                        "start_date": "2026-10-01",
                        "end_date": "2026-10-31",
                        "warehouse_id": 12,
                    },
                    "idempotency_key": "inventory-walkthrough-tool-failed",
                },
            )
            assert tool_failed.status_code == 422
            history = await client.get(f"/api/v1/ecosystem/skills/{skill_id}/runs")
            failed = next(
                item
                for item in history.json()["data"]
                if item["idempotency_key"] == "inventory-walkthrough-tool-failed"
            )
            assert failed["status"] == "FAILED"
            assert failed["output_snapshot"]["tool_calls"][0]["status"] == "FAILED"
    finally:
        app.dependency_overrides.clear()
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_inventory_skill_live_environment() -> None:
    """显式启用的只读真实环境验收；默认跳过，禁止把 Mock 结果冒充真实验收。"""
    required = {
        name: os.getenv(name, "").strip()
        for name in (
            "COPILOT_V14_LIVE_URL",
            "COPILOT_V14_LIVE_TOKEN",
            "COPILOT_V14_LIVE_TENANT_ID",
            "COPILOT_V14_LIVE_SKILL_ID",
            "COPILOT_V14_LIVE_SKU_CODE",
        )
    }
    if not all(required.values()):
        pytest.skip("未配置完整 COPILOT_V14_LIVE_*，跳过真实模型/ERP 环境验收")
    end = date.today()
    start = end.replace(day=1)
    async with httpx.AsyncClient(
        base_url=required["COPILOT_V14_LIVE_URL"], timeout=180
    ) as client:
        response = await client.post(
            f"/api/v1/ecosystem/skills/{required['COPILOT_V14_LIVE_SKILL_ID']}/runs",
            headers={
                "Authorization": f"Bearer {required['COPILOT_V14_LIVE_TOKEN']}",
                "X-Tenant-ID": required["COPILOT_V14_LIVE_TENANT_ID"],
            },
            json={
                "input": {
                    "sku_code": required["COPILOT_V14_LIVE_SKU_CODE"],
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                },
                "idempotency_key": f"inventory-live-{end.isoformat()}",
            },
        )
    assert response.status_code == 200, response.text
    run = response.json()["data"]
    assert run["status"] == "SUCCEEDED"
    assert run["output_snapshot"]["evidence"]
    assert run["output_snapshot"]["tool_calls"]


@pytest.mark.asyncio
async def test_inventory_skill_live_chat_environment() -> None:
    """显式真实验收：真实 Copilot Chat/Selector/模型/ERP；默认不运行。"""
    required = {
        name: os.getenv(name, "").strip()
        for name in (
            "COPILOT_V14_LIVE_URL",
            "COPILOT_V14_LIVE_TOKEN",
            "COPILOT_V14_LIVE_TENANT_ID",
            "COPILOT_V14_LIVE_SKU_CODE",
            "COPILOT_V14_LIVE_START_DATE",
            "COPILOT_V14_LIVE_END_DATE",
        )
    }
    if not all(required.values()):
        pytest.skip("未配置完整 COPILOT_V14_LIVE_*，跳过真实 Chat Skill 验收")
    headers = {
        "Authorization": f"Bearer {required['COPILOT_V14_LIVE_TOKEN']}",
        "X-Tenant-ID": required["COPILOT_V14_LIVE_TENANT_ID"],
    }
    async with httpx.AsyncClient(
        base_url=required["COPILOT_V14_LIVE_URL"], headers=headers, timeout=90
    ) as client:
        created = await client.post("/api/v1/conversations", json={"title": "V14.2 live Skill"})
        created.raise_for_status()
        conversation_id = created.json()["data"]["id"]
        response = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                "client_request_id": f"v142-live-{os.urandom(8).hex()}",
                "message": (
                    f"分析 {required['COPILOT_V14_LIVE_SKU_CODE']} 从"
                    f"{required['COPILOT_V14_LIVE_START_DATE']}到"
                    f"{required['COPILOT_V14_LIVE_END_DATE']}的库存覆盖天数和库存风险"
                ),
            },
        )
        response.raise_for_status()
        assert "event: skill_selected" in response.text
        assert "event: evidence" in response.text
        assert "event: skill_done" in response.text
        detail = await client.get(f"/api/v1/conversations/{conversation_id}")
        detail.raise_for_status()
        assistant = detail.json()["data"]["messages"][-1]
        assert assistant["skill_runs"][0]["status"] == "SUCCEEDED"
        assert assistant["evidences"]
