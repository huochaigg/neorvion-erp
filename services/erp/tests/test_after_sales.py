"""销售售后、退货入库、退款记录。售后不改 SalesOrderItem.quantity，也不回退履约状态。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.schemas.after_sale import AfterSaleCreate, AfterSaleItemIn
from app.services.after_sale import AfterSaleService
from app.services.inventory import InventoryService
from app.services.return_order import ReturnOrderService
from fastapi.testclient import TestClient

from tests.helpers.auth_api import auth_header, register_and_login
from tests.test_sales_orders import (
    _add_member,
    _create_tenant,
    _customer,
    _initialize,
    _member_id,
    _order,
    _product,
    _roles,
    _warehouse,
)


def _header(token: str, tenant_id: int) -> dict[str, str]:
    return auth_header(token, tenant_id)


def _fulfilled(
    client: TestClient,
    token: str,
    tenant_id: int,
    *,
    qty: int = 10,
    stock: int = 100,
    unit_price: float = 10,
    sku_code: str = "AS-A",
    extra_skus: list[dict] | None = None,
) -> dict:
    customer = _customer(client, token, tenant_id, "售后客户")
    warehouse = _warehouse(client, token, tenant_id, "售后仓")
    skus = [{"sku_code": sku_code, "name": "A", "spec_values": {}}, *(extra_skus or [])]
    product = _product(client, token, tenant_id, f"售后货-{sku_code}", skus)
    header = _header(token, tenant_id)
    inventories: dict[int, int] = {}
    items = []
    for sku in product["skus"]:
        line_qty = qty if sku["sku_code"] == sku_code else qty
        inv = _initialize(client, token, tenant_id, warehouse["id"], sku["id"], stock)
        inventories[sku["id"]] = inv.json()["data"]["id"]
        items.append({"sku_id": sku["id"], "quantity": line_qty, "unit_price": unit_price})
    created = _order(
        client,
        token,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=items,
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    outbound = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": order_id},
        headers=header,
    ).json()["data"]["items"][0]
    detail = client.get(f"/api/v1/outbound-orders/{outbound['id']}", headers=header).json()["data"]
    client.post(
        f"/api/v1/outbound-orders/{outbound['id']}/pick",
        json={
            "items": [
                {"id": row["id"], "picked_quantity": row["planned_quantity"]}
                for row in detail["items"]
            ]
        },
        headers=header,
    )
    confirmed = client.post(f"/api/v1/outbound-orders/{outbound['id']}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text
    order = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    return {
        "header": header,
        "order": order,
        "order_id": order_id,
        "warehouse_id": warehouse["id"],
        "customer_id": customer["id"],
        "inventories": inventories,
        "sku_ids": [sku["id"] for sku in product["skus"]],
    }


def _create_as(client: TestClient, data: dict, payload: dict):
    return client.post("/api/v1/after-sales", json=payload, headers=data["header"])


def test_outbounded_order_can_create_three_types(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-types@example.com")
    tenant_id = _create_tenant(client, owner, "AsTypes", "as-types")
    data = _fulfilled(client, owner, tenant_id, qty=10)
    item = data["order"]["items"][0]
    refund_only = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "REFUND_ONLY",
            "reason": "少量补偿",
            "items": [
                {
                    "sales_order_item_id": item["id"],
                    "return_quantity": 0,
                    "requested_refund_amount": "10.00",
                }
            ],
        },
    )
    assert refund_only.status_code == 200, refund_only.text
    assert refund_only.json()["data"]["after_sale_no"].startswith("AS")
    assert refund_only.json()["data"]["status"] == "PENDING_APPROVAL"
    client.post(f"/api/v1/after-sales/{refund_only.json()['data']['id']}/cancel", headers=data["header"])

    ret_only = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_ONLY",
            "reason": "返修",
            "items": [{"sales_order_item_id": item["id"], "return_quantity": 2, "requested_refund_amount": "0"}],
        },
    )
    assert ret_only.status_code == 200, ret_only.text
    client.post(f"/api/v1/after-sales/{ret_only.json()['data']['id']}/cancel", headers=data["header"])

    both = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_AND_REFUND",
            "reason": "质量问题",
            "items": [
                {
                    "sales_order_item_id": item["id"],
                    "return_quantity": 3,
                    "requested_refund_amount": "30.00",
                }
            ],
        },
    )
    assert both.status_code == 200, both.text
    preview = client.get(
        "/api/v1/after-sales/preview",
        params={"sales_order_id": data["order_id"]},
        headers=data["header"],
    ).json()["data"]
    assert preview["items"][0]["returnable_quantity"] == 7
    listed = client.get("/api/v1/after-sales", headers=data["header"]).json()["data"]
    assert listed["total"] >= 1


def test_waiting_outbound_cannot_create_after_sale(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-wait@example.com")
    tenant_id = _create_tenant(client, owner, "AsWait", "as-wait")
    customer = _customer(client, owner, tenant_id, "未出库客户")
    warehouse = _warehouse(client, owner, tenant_id, "未出库仓")
    product = _product(client, owner, tenant_id, "未出库货", [{"sku_code": "WAIT-A", "name": "A", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 20)
    header = _header(owner, tenant_id)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 4, "unit_price": 9}],
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    order = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    assert order["status"] == "WAITING_OUTBOUND"
    refused = client.post(
        "/api/v1/after-sales",
        json={
            "sales_order_id": order_id,
            "type": "RETURN_AND_REFUND",
            "reason": "不能退",
            "items": [
                {
                    "sales_order_item_id": order["items"][0]["id"],
                    "return_quantity": 1,
                    "requested_refund_amount": "9",
                }
            ],
        },
        headers=header,
    )
    assert refused.status_code == 400
    assert refused.json()["data"]["error"] == "AFTER_SALE_ORDER_NOT_ELIGIBLE"


def test_cannot_exceed_outbound_or_stack_over_returnable(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-cap@example.com")
    tenant_id = _create_tenant(client, owner, "AsCap", "as-cap")
    data = _fulfilled(client, owner, tenant_id, qty=6)
    item = data["order"]["items"][0]
    over = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_ONLY",
            "reason": "超量",
            "items": [{"sales_order_item_id": item["id"], "return_quantity": 7, "requested_refund_amount": "0"}],
        },
    )
    assert over.status_code == 400
    assert over.json()["data"]["error"] == "AFTER_SALE_EXCEEDS_RETURNABLE"
    first = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_ONLY",
            "reason": "第一次",
            "items": [{"sales_order_item_id": item["id"], "return_quantity": 4, "requested_refund_amount": "0"}],
        },
    )
    assert first.status_code == 200, first.text
    second = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_ONLY",
            "reason": "第二次超量",
            "items": [{"sales_order_item_id": item["id"], "return_quantity": 3, "requested_refund_amount": "0"}],
        },
    )
    assert second.status_code == 400
    ok_second = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_ONLY",
            "reason": "第二次刚好",
            "items": [{"sales_order_item_id": item["id"], "return_quantity": 2, "requested_refund_amount": "0"}],
        },
    )
    assert ok_second.status_code == 200, ok_second.text


def test_reject_releases_returnable_quantity(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-rej@example.com")
    tenant_id = _create_tenant(client, owner, "AsRej", "as-rej")
    data = _fulfilled(client, owner, tenant_id, qty=10)
    item = data["order"]["items"][0]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_AND_REFUND",
            "reason": "先占住",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 8, "requested_refund_amount": "80"}
            ],
        },
    )
    as_id = created.json()["data"]["id"]
    rejected = client.post(
        f"/api/v1/after-sales/{as_id}/reject",
        json={"reason": "证据不足"},
        headers=data["header"],
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "REJECTED"
    again = client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"])
    assert again.status_code == 400
    retry = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_AND_REFUND",
            "reason": "重新申请",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 8, "requested_refund_amount": "80"}
            ],
        },
    )
    assert retry.status_code == 200, retry.text


def test_approve_partial_and_idempotent(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-apr@example.com")
    tenant_id = _create_tenant(client, owner, "AsApr", "as-apr")
    data = _fulfilled(client, owner, tenant_id, qty=10)
    item = data["order"]["items"][0]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_AND_REFUND",
            "reason": "部分批准",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 5, "requested_refund_amount": "50"}
            ],
        },
    )
    as_id = created.json()["data"]["id"]
    as_item_id = created.json()["data"]["items"][0]["id"]
    over = client.post(
        f"/api/v1/after-sales/{as_id}/approve",
        json={
            "items": [
                {
                    "item_id": as_item_id,
                    "approved_return_quantity": 6,
                    "approved_refund_amount": "50",
                }
            ]
        },
        headers=data["header"],
    )
    assert over.status_code == 400
    approved = client.post(
        f"/api/v1/after-sales/{as_id}/approve",
        json={
            "items": [
                {
                    "item_id": as_item_id,
                    "approved_return_quantity": 3,
                    "approved_refund_amount": "20",
                }
            ]
        },
        headers=data["header"],
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()["data"]
    assert body["status"] == "WAITING_RETURN"
    assert body["approved_refund_amount"] == 20
    assert body["return_order_id"]
    again = client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"])
    assert again.status_code == 400
    assert again.json()["data"]["error"] == "AFTER_SALE_ALREADY_APPROVED"
    returns = client.get(
        "/api/v1/return-orders",
        params={"after_sale_id": as_id},
        headers=data["header"],
    ).json()["data"]["items"]
    assert len(returns) == 1
    assert returns[0]["expected_quantity"] == 3


def test_refund_only_skips_return_and_completes(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-rf@example.com")
    tenant_id = _create_tenant(client, owner, "AsRf", "as-rf")
    data = _fulfilled(client, owner, tenant_id, qty=10)
    item = data["order"]["items"][0]
    inv_before = client.get(
        f"/api/v1/inventory/{data['inventories'][data['sku_ids'][0]]}",
        headers=data["header"],
    ).json()["data"]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "REFUND_ONLY",
            "reason": "补偿",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 0, "requested_refund_amount": "15"}
            ],
        },
    )
    as_id = created.json()["data"]["id"]
    approved = client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"])
    assert approved.json()["data"]["status"] == "WAITING_REFUND"
    returns = client.get(
        "/api/v1/return-orders",
        params={"after_sale_id": as_id},
        headers=data["header"],
    ).json()["data"]["items"]
    assert returns == []
    failed = client.post(
        f"/api/v1/after-sales/{as_id}/refunds",
        json={"amount": "15"},
        headers=data["header"],
    )
    refund_id = failed.json()["data"]["id"]
    assert failed.json()["data"]["refund_no"].startswith("RF")
    marked = client.post(
        f"/api/v1/refunds/{refund_id}/fail",
        json={"failure_reason": "渠道超时"},
        headers=data["header"],
    )
    assert marked.json()["data"]["status"] == "FAILED"
    after = client.get(f"/api/v1/after-sales/{as_id}", headers=data["header"]).json()["data"]
    assert after["status"] == "WAITING_REFUND"
    retry = client.post(
        f"/api/v1/after-sales/{as_id}/refunds",
        json={"amount": "15", "external_reference_no": "PAY-1"},
        headers=data["header"],
    )
    success = client.post(f"/api/v1/refunds/{retry.json()['data']['id']}/confirm", json={}, headers=data["header"])
    assert success.status_code == 200, success.text
    done = client.get(f"/api/v1/after-sales/{as_id}", headers=data["header"]).json()["data"]
    assert done["status"] == "COMPLETED"
    assert done["refund_status"] == "SUCCESS"
    again = client.post(
        f"/api/v1/refunds/{retry.json()['data']['id']}/confirm",
        json={},
        headers=data["header"],
    )
    assert again.status_code == 400
    inv_after = client.get(
        f"/api/v1/inventory/{data['inventories'][data['sku_ids'][0]]}",
        headers=data["header"],
    ).json()["data"]
    assert inv_after["quantity"] == inv_before["quantity"]
    order = client.get(f"/api/v1/sales-orders/{data['order_id']}", headers=data["header"]).json()["data"]
    assert order["status"] == data["order"]["status"]
    assert order["items"][0]["quantity"] == 10


def test_return_and_refund_cannot_refund_before_inbound(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-seq@example.com")
    tenant_id = _create_tenant(client, owner, "AsSeq", "as-seq")
    data = _fulfilled(client, owner, tenant_id, qty=5)
    item = data["order"]["items"][0]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_AND_REFUND",
            "reason": "先退货",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 5, "requested_refund_amount": "50"}
            ],
        },
    )
    as_id = created.json()["data"]["id"]
    client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"])
    blocked = client.post(f"/api/v1/after-sales/{as_id}/refunds", json={}, headers=data["header"])
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "AFTER_SALE_RETURN_NOT_READY"


def test_return_receive_inbound_and_conditions(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-inb@example.com")
    tenant_id = _create_tenant(client, owner, "AsInb", "as-inb")
    data = _fulfilled(client, owner, tenant_id, qty=5)
    sku_id = data["sku_ids"][0]
    inventory_id = data["inventories"][sku_id]
    before = client.get(f"/api/v1/inventory/{inventory_id}", headers=data["header"]).json()["data"]
    item = data["order"]["items"][0]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_AND_REFUND",
            "reason": "退货入库",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 5, "requested_refund_amount": "50"}
            ],
        },
    )
    as_id = created.json()["data"]["id"]
    approved = client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"]).json()["data"]
    return_id = approved["return_order_id"]
    detail = client.get(f"/api/v1/return-orders/{return_id}", headers=data["header"]).json()["data"]
    line_id = detail["items"][0]["id"]
    over = client.post(
        f"/api/v1/return-orders/{return_id}/receive",
        json={"items": [{"item_id": line_id, "received_quantity": 6, "condition": "GOOD"}]},
        headers=data["header"],
    )
    assert over.status_code == 400
    part = client.post(
        f"/api/v1/return-orders/{return_id}/receive",
        json={"items": [{"item_id": line_id, "received_quantity": 3, "condition": "GOOD"}]},
        headers=data["header"],
    )
    assert part.json()["data"]["status"] == "PARTIALLY_RECEIVED"
    rest = client.post(
        f"/api/v1/return-orders/{return_id}/receive",
        json={"items": [{"item_id": line_id, "received_quantity": 2, "condition": "GOOD"}]},
        headers=data["header"],
    )
    assert rest.json()["data"]["status"] == "RECEIVED"
    inbound = client.post(f"/api/v1/return-orders/{return_id}/confirm-inbound", headers=data["header"])
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["data"]["status"] == "INBOUNDED"
    after = client.get(f"/api/v1/inventory/{inventory_id}", headers=data["header"]).json()["data"]
    assert after["quantity"] == before["quantity"] + 5
    assert after["reserved_quantity"] == before["reserved_quantity"]
    txs = client.get(f"/api/v1/inventory/{inventory_id}/transactions", headers=data["header"]).json()["data"]["items"]
    inbound_tx = [row for row in txs if row["type"] == "RETURN_INBOUND"]
    assert inbound_tx
    assert inbound_tx[0]["change_quantity"] == 5
    assert inbound_tx[0]["before_reserved_quantity"] == inbound_tx[0]["after_reserved_quantity"]
    repeat = client.post(f"/api/v1/return-orders/{return_id}/confirm-inbound", headers=data["header"])
    assert repeat.status_code == 400
    assert repeat.json()["data"]["error"] == "RETURN_ALREADY_INBOUNDED"
    waiting = client.get(f"/api/v1/after-sales/{as_id}", headers=data["header"]).json()["data"]
    assert waiting["status"] == "WAITING_REFUND"
    refund = client.post(f"/api/v1/after-sales/{as_id}/refunds", json={}, headers=data["header"])
    client.post(f"/api/v1/refunds/{refund.json()['data']['id']}/confirm", json={}, headers=data["header"])
    done = client.get(f"/api/v1/after-sales/{as_id}", headers=data["header"]).json()["data"]
    assert done["status"] == "COMPLETED"
    order = client.get(f"/api/v1/sales-orders/{data['order_id']}", headers=data["header"]).json()["data"]
    assert order["status"] == data["order"]["status"]


def test_damaged_does_not_increase_ordinary_inventory(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-dmg@example.com")
    tenant_id = _create_tenant(client, owner, "AsDmg", "as-dmg")
    data = _fulfilled(client, owner, tenant_id, qty=4)
    inventory_id = data["inventories"][data["sku_ids"][0]]
    before = client.get(f"/api/v1/inventory/{inventory_id}", headers=data["header"]).json()["data"]
    item = data["order"]["items"][0]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_ONLY",
            "reason": "损坏",
            "items": [{"sales_order_item_id": item["id"], "return_quantity": 4, "requested_refund_amount": "0"}],
        },
    )
    as_id = created.json()["data"]["id"]
    approved = client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"]).json()["data"]
    return_id = approved["return_order_id"]
    line_id = client.get(f"/api/v1/return-orders/{return_id}", headers=data["header"]).json()["data"]["items"][0]["id"]
    client.post(
        f"/api/v1/return-orders/{return_id}/receive",
        json={"items": [{"item_id": line_id, "received_quantity": 4, "condition": "DAMAGED"}]},
        headers=data["header"],
    )
    inbound = client.post(f"/api/v1/return-orders/{return_id}/confirm-inbound", headers=data["header"])
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["data"]["status"] == "INBOUNDED"
    assert inbound.json()["data"]["inbound_quantity"] == 0
    after = client.get(f"/api/v1/inventory/{inventory_id}", headers=data["header"]).json()["data"]
    assert after["quantity"] == before["quantity"]
    done = client.get(f"/api/v1/after-sales/{as_id}", headers=data["header"]).json()["data"]
    assert done["status"] == "COMPLETED"
    no_refund = client.post(f"/api/v1/after-sales/{as_id}/refunds", json={}, headers=data["header"])
    assert no_refund.status_code == 400
    unsell = _fulfilled(client, owner, tenant_id, qty=2, sku_code="AS-U")
    u_item = unsell["order"]["items"][0]
    created_u = _create_as(
        client,
        unsell,
        {
            "sales_order_id": unsell["order_id"],
            "type": "RETURN_ONLY",
            "reason": "不可售",
            "items": [{"sales_order_item_id": u_item["id"], "return_quantity": 2, "requested_refund_amount": "0"}],
        },
    )
    as_u = created_u.json()["data"]["id"]
    ap_u = client.post(f"/api/v1/after-sales/{as_u}/approve", json={}, headers=unsell["header"]).json()["data"]
    rid = ap_u["return_order_id"]
    lid = client.get(f"/api/v1/return-orders/{rid}", headers=unsell["header"]).json()["data"]["items"][0]["id"]
    client.post(
        f"/api/v1/return-orders/{rid}/receive",
        json={"items": [{"item_id": lid, "received_quantity": 2, "condition": "UNSELLABLE"}]},
        headers=unsell["header"],
    )
    inb = client.post(f"/api/v1/return-orders/{rid}/confirm-inbound", headers=unsell["header"])
    assert inb.json()["data"]["inbound_quantity"] == 0


def test_inbound_multi_sku_failure_rolls_back(client: TestClient, monkeypatch) -> None:
    owner, _ = register_and_login(client, "as-atom@example.com")
    tenant_id = _create_tenant(client, owner, "AsAtom", "as-atom")
    data = _fulfilled(
        client,
        owner,
        tenant_id,
        qty=2,
        extra_skus=[{"sku_code": "AS-B", "name": "B", "spec_values": {}}],
    )
    first_inv = client.get(
        f"/api/v1/inventory/{data['inventories'][data['sku_ids'][0]]}",
        headers=data["header"],
    ).json()["data"]["quantity"]
    items_payload = [
        {
            "sales_order_item_id": row["id"],
            "return_quantity": 2,
            "requested_refund_amount": "0",
        }
        for row in data["order"]["items"]
    ]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_ONLY",
            "reason": "多 SKU",
            "items": items_payload,
        },
    )
    as_id = created.json()["data"]["id"]
    approved = client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"]).json()["data"]
    return_id = approved["return_order_id"]
    detail = client.get(f"/api/v1/return-orders/{return_id}", headers=data["header"]).json()["data"]
    client.post(
        f"/api/v1/return-orders/{return_id}/receive",
        json={
            "items": [
                {"item_id": row["id"], "received_quantity": 2, "condition": "GOOD"} for row in detail["items"]
            ]
        },
        headers=data["header"],
    )
    original = InventoryService.inbound_within_transaction
    calls = {"n": 0}

    def _fail_second(self, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise AppError(message="第二行失败", status_code=400, data={"error": "FORCED"})
        return original(self, **kwargs)

    monkeypatch.setattr(InventoryService, "inbound_within_transaction", _fail_second)
    failed = client.post(f"/api/v1/return-orders/{return_id}/confirm-inbound", headers=data["header"])
    assert failed.status_code == 400
    after = client.get(
        f"/api/v1/inventory/{data['inventories'][data['sku_ids'][0]]}",
        headers=data["header"],
    ).json()["data"]
    assert after["quantity"] == first_inv
    ret = client.get(f"/api/v1/return-orders/{return_id}", headers=data["header"]).json()["data"]
    assert ret["status"] != "INBOUNDED"


def test_concurrent_after_sale_and_inbound(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-cc@example.com")
    tenant_id = _create_tenant(client, owner, "AsCc", "as-cc")
    user_id, member_id = _member_id(client, owner, tenant_id)
    data = _fulfilled(client, owner, tenant_id, qty=10)
    item_id = data["order"]["items"][0]["id"]
    payload = AfterSaleCreate(
        sales_order_id=data["order_id"],
        type="RETURN_ONLY",
        reason="并发",
        items=[AfterSaleItemIn(sales_order_item_id=item_id, return_quantity=8, requested_refund_amount=Decimal("0"))],
    )

    def _create(_: int) -> str:
        session = SessionLocal()
        try:
            AfterSaleService(
                session,
                TenantContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    member_id=member_id,
                    is_owner=True,
                    role=MemberRole.OWNER.value,
                ),
            ).create_after_sale(payload)
            return "ok"
        except AppError as exc:
            return str(exc.data.get("error", exc.code) if exc.data else exc.code)
        except Exception as exc:
            return type(exc).__name__
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_create, [1, 2]))
    assert results.count("ok") == 1
    assert "AFTER_SALE_EXCEEDS_RETURNABLE" in results

    listed = client.get(
        "/api/v1/after-sales",
        params={"sales_order_id": data["order_id"]},
        headers=data["header"],
    ).json()["data"]["items"]
    as_id = listed[0]["id"]
    approved = client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"]).json()["data"]
    return_id = approved["return_order_id"]
    detail = client.get(f"/api/v1/return-orders/{return_id}", headers=data["header"]).json()["data"]
    client.post(
        f"/api/v1/return-orders/{return_id}/receive",
        json={
            "items": [
                {
                    "item_id": detail["items"][0]["id"],
                    "received_quantity": detail["items"][0]["expected_quantity"],
                    "condition": "GOOD",
                }
            ]
        },
        headers=data["header"],
    )

    def _inbound(_: int) -> str:
        session = SessionLocal()
        try:
            ReturnOrderService(
                session,
                TenantContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    member_id=member_id,
                    is_owner=True,
                    role=MemberRole.OWNER.value,
                ),
            ).confirm_inbound(return_id)
            return "ok"
        except AppError as exc:
            return str(exc.data.get("error", exc.code) if exc.data else exc.code)
        except Exception as exc:
            return type(exc).__name__
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        inbound_results = list(pool.map(_inbound, [1, 2]))
    assert inbound_results.count("ok") == 1


def test_cross_tenant_hidden_and_rbac(client: TestClient) -> None:
    owner, _ = register_and_login(client, "as-rbac@example.com")
    tenant_id = _create_tenant(client, owner, "AsRbac", "as-rbac")
    data = _fulfilled(client, owner, tenant_id, qty=3)
    item = data["order"]["items"][0]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "REFUND_ONLY",
            "reason": "隔离",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 0, "requested_refund_amount": "5"}
            ],
        },
    )
    as_id = created.json()["data"]["id"]
    other, _ = register_and_login(client, "as-rbac-b@example.com")
    other_tenant = _create_tenant(client, other, "AsRbacB", "as-rbac-b")
    hidden = client.get(f"/api/v1/after-sales/{as_id}", headers=_header(other, other_tenant))
    assert hidden.status_code == 404

    roles = _roles(client, owner, tenant_id)
    viewer = _add_member(client, owner, tenant_id, "as-view@example.com", [roles["VIEWER"]["id"]])
    operator = _add_member(client, owner, tenant_id, "as-op@example.com", [roles["OPERATOR"]["id"]])
    warehouse = _add_member(client, owner, tenant_id, "as-wh@example.com", [roles["WAREHOUSE"]["id"]])
    viewer_list = client.get("/api/v1/after-sales", headers=_header(viewer, tenant_id))
    assert viewer_list.status_code == 200
    denied_create = client.post(
        "/api/v1/after-sales",
        json={
            "sales_order_id": data["order_id"],
            "type": "REFUND_ONLY",
            "reason": "无权限",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 0, "requested_refund_amount": "1"}
            ],
        },
        headers=_header(viewer, tenant_id),
    )
    assert denied_create.status_code == 403
    op_create = client.post(
        "/api/v1/after-sales",
        json={
            "sales_order_id": data["order_id"],
            "type": "REFUND_ONLY",
            "reason": "运营可建",
            "items": [
                {"sales_order_item_id": item["id"], "return_quantity": 0, "requested_refund_amount": "1"}
            ],
        },
        headers=_header(operator, tenant_id),
    )
    assert op_create.status_code == 200, op_create.text
    denied_approve = client.post(
        f"/api/v1/after-sales/{op_create.json()['data']['id']}/approve",
        json={},
        headers=_header(operator, tenant_id),
    )
    assert denied_approve.status_code == 403
    catalog = {item["code"] for item in roles["WAREHOUSE"]["permissions"]}
    assert PermissionCode.RETURN_ORDER_INBOUND in catalog
    assert PermissionCode.REFUND_CONFIRM not in catalog
    client.post(f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"])
    refund = client.post(f"/api/v1/after-sales/{as_id}/refunds", json={}, headers=data["header"])
    denied_confirm = client.post(
        f"/api/v1/refunds/{refund.json()['data']['id']}/confirm",
        json={},
        headers=_header(warehouse, tenant_id),
    )
    assert denied_confirm.status_code == 403
    codes = {item["code"] for item in roles["OPERATOR"]["permissions"]}
    assert PermissionCode.AFTER_SALE_CREATE in codes
    assert PermissionCode.AFTER_SALE_APPROVE not in codes
