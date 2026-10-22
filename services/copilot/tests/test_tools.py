from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from app.ai.types import ChatDelta, ModelMessage, ModelToolCall, ModelToolDefinition
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.erp.client import ErpApiClient
from app.graph.workflow import AgentRuntime, CopilotWorkflow
from app.tools.executor import ToolExecutor, ToolRuntime
from app.tools.registry import build_tool_registry

from conftest import make_context


def make_client(handler) -> ErpApiClient:
    return ErpApiClient(
        base_url="https://erp.test",
        connect_timeout=1,
        read_timeout=1,
        transport=httpx.MockTransport(handler),
    )


def runtime(*permissions: str, token: str = "user-token", audience: bool = True) -> ToolRuntime:
    return ToolRuntime(
        tenant=make_context(extra_permissions=set(permissions)),
        access_token=token,
        erp_audience_authorized=audience,
    )


@pytest.mark.asyncio
async def test_inventory_tool_forwards_verified_identity_and_filters_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer user-token"
        assert request.headers["X-Tenant-ID"] == "7"
        assert request.url.params["sku_code"] == "SKU-1"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "message": "ok",
                "data": {
                    "items": [
                        {
                            "id": 1,
                            "tenant_id": 7,
                            "sku_code": "SKU-1",
                            "quantity": 9,
                            "reserved_quantity": 2,
                            "available_quantity": 7,
                            "secret": "drop-me",
                        }
                    ],
                    "total": 1,
                    "page": 1,
                    "page_size": 20,
                },
            },
        )

    erp = make_client(handler)
    executor = ToolExecutor(build_tool_registry(), erp)
    result = await executor.execute(
        ModelToolCall(id="c1", name="get_inventory", arguments='{"sku_code":"SKU-1"}'),
        runtime(PermissionCode.INVENTORY_READ.value),
    )
    assert '"available_quantity":7' in result.content
    assert "tenant_id" not in result.content
    assert "secret" not in result.content
    await erp.aclose()


@pytest.mark.asyncio
async def test_tool_rejects_permission_tenant_argument_and_non_erp_token() -> None:
    erp = make_client(lambda request: httpx.Response(500))
    executor = ToolExecutor(build_tool_registry(), erp)
    call = ModelToolCall(id="c1", name="get_sales_order", arguments='{"order_id":1}')
    with pytest.raises(AppError, match="无权") as denied:
        await executor.execute(call, runtime())
    assert denied.value.code == 40372
    with pytest.raises(AppError) as bad_tenant:
        await executor.execute(
            ModelToolCall(
                id="c2",
                name="get_sales_order",
                arguments='{"order_id":1,"tenant_id":8}',
            ),
            runtime(PermissionCode.ORDER_READ.value),
        )
    assert bad_tenant.value.code == 40071
    with pytest.raises(AppError) as bad_audience:
        await executor.execute(call, runtime(PermissionCode.ORDER_READ.value, audience=False))
    assert bad_audience.value.code == 40373
    await erp.aclose()


class ToolThenAnswerAdapter:
    def __init__(self) -> None:
        self.turn = 0

    async def stream(
        self,
        messages: list[ModelMessage],
        *,
        tools: list[ModelToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ChatDelta]:
        self.turn += 1
        if self.turn == 1:
            yield ChatDelta(
                finished=True,
                tool_calls=(
                    ModelToolCall(
                        id="call-1", name="get_inventory", arguments='{"sku_code":"SKU-1"}'
                    ),
                ),
            )
            return
        tool_message = next(item for item in messages if item["role"] == "tool")
        assert "untrusted_erp_tool_result" in str(tool_message["content"])
        yield ChatDelta(text="SKU-1 可用库存为 7。")
        yield ChatDelta(finished=True)


@pytest.mark.asyncio
async def test_graph_tool_loop_emits_lifecycle_events() -> None:
    erp = make_client(
        lambda request: httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [{"sku_code": "SKU-1", "available_quantity": 7}],
                    "total": 1,
                    "page": 1,
                    "page_size": 20,
                },
            },
        )
    )
    workflow = CopilotWorkflow(ToolThenAnswerAdapter(), ToolExecutor(build_tool_registry(), erp))
    context = AgentRuntime(tools=runtime(PermissionCode.INVENTORY_READ.value))
    events = [
        event
        async for event in workflow.stream(
            [{"role": "user", "content": "SKU-1 库存"}], context=context
        )
    ]
    assert [event["event"] for event in events] == [
        "tool_start",
        "tool_end",
        "message",
        "done",
    ]
    assert events[-1]["data"]["answer"] == "SKU-1 可用库存为 7。"
    await erp.aclose()


@pytest.mark.asyncio
async def test_unregistered_write_tool_is_not_executed() -> None:
    erp = make_client(lambda request: pytest.fail("illegal tool must not reach ERP"))
    executor = ToolExecutor(build_tool_registry(), erp)
    with pytest.raises(AppError) as captured:
        await executor.execute(
            ModelToolCall(
                id="c1", name="delete_sales_order", arguments=json.dumps({"id": 1})
            ),
            runtime(PermissionCode.ORDER_READ.value),
        )
    assert captured.value.code == 40072
    await erp.aclose()


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, 40370), (403, 40370), (404, 40470), (429, 42970), (500, 50270)],
)
@pytest.mark.asyncio
async def test_erp_http_errors_are_sanitized(status: int, code: int) -> None:
    erp = make_client(lambda request: httpx.Response(status, text="internal secret"))
    executor = ToolExecutor(build_tool_registry(), erp)
    with pytest.raises(AppError) as captured:
        await executor.execute(
            ModelToolCall(id="c1", name="get_sales_order", arguments='{"order_id":1}'),
            runtime(PermissionCode.ORDER_READ.value),
        )
    assert captured.value.code == code
    assert "secret" not in captured.value.message
    await erp.aclose()


def test_sse_api_includes_tool_lifecycle_events(client, authorize, use_workflow) -> None:
    erp = make_client(
        lambda request: httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [{"sku_code": "SKU-1", "available_quantity": 7}],
                    "total": 1,
                    "page": 1,
                    "page_size": 20,
                },
            },
        )
    )
    authorize(extra_permissions={PermissionCode.INVENTORY_READ.value})
    use_workflow(
        CopilotWorkflow(ToolThenAnswerAdapter(), ToolExecutor(build_tool_registry(), erp))
    )
    response = client.post(
        "/api/v1/chat/stream",
        json={"messages": [{"role": "user", "content": "SKU-1 库存"}]},
    )
    assert response.status_code == 200
    assert "event: tool_start" in response.text
    assert "event: tool_end" in response.text
    assert "event: done" in response.text
