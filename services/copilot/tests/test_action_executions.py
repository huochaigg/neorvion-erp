from __future__ import annotations

import hashlib
import hmac

import httpx
import pytest
from app.core.config import settings
from app.core.exceptions import AppError
from app.erp.client import ErpApiClient
from app.executions.registry import build_execution_registry
from app.tools.registry import build_tool_registry


def test_execution_registry_is_closed_and_not_exposed_to_llm() -> None:
    registry = build_execution_registry()
    purchase = registry.get("PURCHASE_ORDER_CREATE")
    transfer = registry.get("INVENTORY_TRANSFER_CREATE")
    assert purchase.execute_path == "/api/v1/action-executions/purchase-order"
    assert purchase.requires_approval is False
    assert transfer.requires_approval is True
    assert transfer.risk_level == "HIGH"
    with pytest.raises(ValueError, match="未注册"):
        registry.get("INVENTORY_ADJUST")
    assert build_tool_registry().get("execute_action") is None


@pytest.mark.asyncio
async def test_erp_execute_uses_bound_signature_and_fixed_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "unit-test-execution-secret-at-least-32-bytes"
    monkeypatch.setattr(
        settings, "erp_execution_secret", type(settings.erp_execution_secret)(secret)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/action-executions/purchase-order"
        body = __import__("json").loads(request.content)
        expires = request.headers["X-Copilot-Execution-Expires"]
        claim = "\n".join(
            map(
                str,
                (
                    7,
                    11,
                    body["action_type"],
                    body["execution_key"],
                    body["proposal_revision"],
                    body["payload_hash"],
                    expires,
                ),
            )
        )
        expected = hmac.new(secret.encode(), claim.encode(), hashlib.sha256).hexdigest()
        assert hmac.compare_digest(request.headers["X-Copilot-Execution-Signature"], expected)
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "status": "SUCCEEDED",
                    "resource_type": "PURCHASE_ORDER",
                    "resource_id": 9,
                    "resource_no": "PO9",
                },
            },
        )

    client = ErpApiClient(
        base_url="https://erp.test",
        connect_timeout=1,
        read_timeout=1,
        transport=httpx.MockTransport(handler),
    )
    payload = {"supplier_id": 1, "warehouse_id": 2, "items": [{"sku_id": 3, "quantity": 1}]}
    digest = hashlib.sha256(
        __import__("json")
        .dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .encode()
    ).hexdigest()
    result = await client.execute(
        "/api/v1/action-executions/purchase-order",
        execution_key="cpx_unit_test_0001",
        action_type="PURCHASE_ORDER_CREATE",
        revision=1,
        payload_hash=digest,
        payload=payload,
        user_id=11,
        access_token="user-token",
        tenant_id=7,
    )
    assert result["resource_id"] == 9
    with pytest.raises(AppError, match="未注册"):
        await client.execute(
            "https://evil.example/write",
            execution_key="x",
            action_type="PURCHASE_ORDER_CREATE",
            revision=1,
            payload_hash=digest,
            payload=payload,
            user_id=11,
            access_token="token",
            tenant_id=7,
        )
    await client.aclose()
