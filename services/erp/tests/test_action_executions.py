import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.execution_auth import canonical_execution_claim
from app.db.session import SessionLocal
from app.models.action_execution import ErpActionExecutionReceipt
from app.models.purchase import PurchaseOrder
from app.models.sales_order import SalesOrder
from app.models.stock_transfer import StockTransfer
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.helpers.auth_api import auth_header, register_and_login
from tests.test_purchase import _create_product, _create_supplier, _create_tenant, _create_warehouse
from tests.test_sales_orders import _customer, _initialize

SECRET = "test-only-copilot-execution-secret-32-bytes"


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _execute_headers(token: str, tenant_id: int, user_id: int, body: dict) -> dict[str, str]:
    expires = int(time.time()) + 60
    claim = canonical_execution_claim(
        tenant_id=tenant_id,
        user_id=user_id,
        action_type=body["action_type"],
        execution_key=body["execution_key"],
        proposal_revision=body["proposal_revision"],
        payload_hash=body["payload_hash"],
        expires_at=expires,
    )
    signature = hmac.new(SECRET.encode(), claim.encode(), hashlib.sha256).hexdigest()
    return {
        **auth_header(token, tenant_id),
        "X-Copilot-Execution-Signature": signature,
        "X-Copilot-Execution-Expires": str(expires),
    }


def test_purchase_execution_is_finally_idempotent_and_signed(client: TestClient) -> None:
    token, user_id = register_and_login(client, "execute-purchase@example.com")
    tenant_id = _create_tenant(client, token, "Execute", "execute-purchase")
    warehouse = _create_warehouse(client, token, tenant_id, "执行仓")
    supplier = _create_supplier(client, token, tenant_id, "执行供应商")
    product = _create_product(
        client,
        token,
        tenant_id,
        "执行商品",
        [{"sku_code": "EXEC-1", "name": "默认", "spec_values": {}}],
    )
    payload = {
        "supplier_id": supplier["id"],
        "warehouse_id": warehouse["id"],
        "items": [{"sku_id": product["skus"][0]["id"], "quantity": 3}],
    }
    body = {
        "execution_key": "cpx_purchase_concurrency_001",
        "action_type": "PURCHASE_ORDER_CREATE",
        "proposal_revision": 1,
        "payload_hash": _payload_hash(payload),
        "payload": payload,
    }
    unsigned = client.post(
        "/api/v1/action-executions/purchase-order", json=body, headers=auth_header(token, tenant_id)
    )
    assert unsigned.status_code == 422

    def send() -> tuple[int, dict]:
        response = client.post(
            "/api/v1/action-executions/purchase-order",
            json=body,
            headers=_execute_headers(token, tenant_id, user_id, body),
        )
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _index: send(), range(10)))
    assert {status for status, _ in results} == {200}, results
    resource_ids = {item["data"]["resource_id"] for _, item in results}
    assert len(resource_ids) == 1
    session = SessionLocal()
    try:
        assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1
        assert session.scalar(select(func.count()).select_from(ErpActionExecutionReceipt)) == 1
    finally:
        session.close()

    changed = {**body, "payload": {**payload, "remark": "different"}}
    changed["payload_hash"] = _payload_hash(changed["payload"])
    conflict = client.post(
        "/api/v1/action-executions/purchase-order",
        json=changed,
        headers=_execute_headers(token, tenant_id, user_id, changed),
    )
    assert conflict.status_code == 409


def test_sales_and_transfer_execution_create_drafts_only(client: TestClient) -> None:
    token, user_id = register_and_login(client, "execute-other@example.com")
    tenant_id = _create_tenant(client, token, "ExecuteOther", "execute-other")
    source = _create_warehouse(client, token, tenant_id, "源仓")
    target = _create_warehouse(client, token, tenant_id, "目标仓")
    customer = _customer(client, token, tenant_id, "执行客户")
    product = _create_product(
        client,
        token,
        tenant_id,
        "执行商品",
        [{"sku_code": "EXEC-OTHER", "name": "默认", "spec_values": {}}],
    )
    sku_id = product["skus"][0]["id"]
    initialized = _initialize(client, token, tenant_id, source["id"], sku_id, 20)
    assert initialized.status_code == 200

    cases = [
        (
            "/api/v1/action-executions/sales-order",
            "SALES_ORDER_CREATE",
            "cpx_sales_execution_0001",
            {
                "customer_id": customer["id"],
                "warehouse_id": source["id"],
                "items": [{"sku_id": sku_id, "quantity": 2, "unit_price": 10}],
            },
        ),
        (
            "/api/v1/action-executions/inventory-transfer",
            "INVENTORY_TRANSFER_CREATE",
            "cpx_transfer_execution_0001",
            {
                "source_warehouse_id": source["id"],
                "target_warehouse_id": target["id"],
                "items": [{"sku_id": sku_id, "quantity": 5}],
            },
        ),
    ]
    for path, action_type, key, payload in cases:
        body = {
            "execution_key": key,
            "action_type": action_type,
            "proposal_revision": 3,
            "payload_hash": _payload_hash(payload),
            "payload": payload,
        }
        response = client.post(
            path, json=body, headers=_execute_headers(token, tenant_id, user_id, body)
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "SUCCEEDED"

    session = SessionLocal()
    try:
        sales = session.scalars(select(SalesOrder)).one()
        transfer = session.scalars(select(StockTransfer)).one()
        assert sales.status == "DRAFT"
        assert transfer.status == "DRAFT"
    finally:
        session.close()
