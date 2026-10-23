from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from app.actions.registry import build_action_registry
from app.ai.types import ModelToolCall
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.erp.client import ErpApiClient
from app.schemas.action_proposal import ActionProposalCreate
from app.tools.executor import ToolExecutor, ToolRuntime
from app.tools.registry import build_tool_registry
from pydantic import ValidationError

from conftest import make_context


def test_action_registry_has_preview_only_contracts() -> None:
    registry = build_action_registry()
    assert {item.action_type for item in registry.all()} == {
        "PURCHASE_ORDER_CREATE",
        "SALES_ORDER_CREATE",
        "INVENTORY_TRANSFER_CREATE",
    }
    assert all("action-previews" in item.preview_path for item in registry.all())
    assert all(not hasattr(item, "execute_handler") for item in registry.all())


def test_proposal_schema_is_typed_and_rejects_trusted_context() -> None:
    parsed = ActionProposalCreate.model_validate(
        {
            "conversation_id": 1,
            "idempotency_key": "request-123",
            "action": {
                "action_type": "PURCHASE_ORDER_CREATE",
                "payload": {"items": [{"sku_id": 2, "quantity": 10}]},
            },
        }
    )
    assert parsed.action.action_type == "PURCHASE_ORDER_CREATE"
    with pytest.raises(ValidationError):
        ActionProposalCreate.model_validate(
            {
                "conversation_id": 1,
                "idempotency_key": "request-123",
                "action": {
                    "action_type": "PURCHASE_ORDER_CREATE",
                    "payload": {
                        "tenant_id": 999,
                        "items": [{"sku_id": 2, "quantity": 10}],
                    },
                },
            }
        )


@pytest.mark.asyncio
async def test_erp_preview_client_forwards_identity_and_blocks_arbitrary_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer user-token"
        assert request.headers["X-Tenant-ID"] == "7"
        assert request.url.path == "/api/v1/action-previews/purchase-order"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "valid": True,
                    "blocking_errors": [],
                    "warnings": [],
                    "missing_fields": [],
                    "normalized_payload": {},
                    "preview_summary": {},
                    "resource_versions": {},
                },
            },
        )

    client = ErpApiClient(
        base_url="https://erp.test",
        connect_timeout=1,
        read_timeout=1,
        transport=httpx.MockTransport(handler),
    )
    result = await client.preview(
        "/api/v1/action-previews/purchase-order",
        payload={},
        access_token="user-token",
        tenant_id=7,
    )
    assert result["valid"] is True
    with pytest.raises(AppError, match="未注册"):
        await client.preview(
            "/api/v1/purchase-orders",
            payload={},
            access_token="user-token",
            tenant_id=7,
        )
    await client.aclose()


def test_action_definitions_follow_current_permissions() -> None:
    registry = build_action_registry()
    assert registry.definitions(frozenset()) == []
    definitions = registry.definitions(frozenset({PermissionCode.PURCHASE_CREATE.value}))
    assert {item["function"]["name"] for item in definitions} == {
        "propose_action",
        "validate_action_proposal",
    }


class _FakeProposalService:
    def __init__(self) -> None:
        self.ids: dict[str, int] = {}

    async def create(self, data):
        proposal_id = self.ids.setdefault(data.idempotency_key, len(self.ids) + 1)
        return SimpleNamespace(
            id=proposal_id,
            current_revision=1,
            action_type=data.action.action_type,
            status="DRAFT",
            validation=None,
        )

    async def validate(self, proposal_id: int, revision: int):
        return SimpleNamespace(
            id=proposal_id,
            current_revision=revision,
            action_type="PURCHASE_ORDER_CREATE",
            status="READY",
            validation=SimpleNamespace(status="VALID", missing_fields=[]),
        )


@pytest.mark.asyncio
async def test_proposal_tool_uses_stable_call_id_and_emits_safe_event() -> None:
    erp = ErpApiClient(
        base_url="https://erp.test",
        connect_timeout=1,
        read_timeout=1,
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )
    proposal_service = _FakeProposalService()
    runtime = ToolRuntime(
        tenant=make_context(extra_permissions={PermissionCode.PURCHASE_CREATE.value}),
        access_token="user-token",
        erp_audience_authorized=True,
        proposal_service=proposal_service,  # type: ignore[arg-type]
        conversation_id=8,
        source_message_id=12,
    )
    executor = ToolExecutor(build_tool_registry(), erp)
    call = ModelToolCall(
        id="stable-call",
        name="propose_action",
        arguments='{"action":{"action_type":"PURCHASE_ORDER_CREATE","payload":{"supplier_id":3,"warehouse_id":2,"items":[{"sku_id":8,"quantity":10}]}}}',
    )
    first = await executor.execute(call, runtime)
    second = await executor.execute(call, runtime)
    assert first.event["proposal_id"] == second.event["proposal_id"] == 1
    assert first.event["proposal_event"] == "proposal_validation"
    assert "payload" not in first.event
    await erp.aclose()
