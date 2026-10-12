"""ERP Core V1 跨领域主链路。验证库存、单据、状态真正串起来。"""

from __future__ import annotations

from app.services.analytics import _csv_cell
from fastapi.testclient import TestClient

from tests.helpers.auth_api import register_and_login
from tests.helpers.factory import bootstrap
from tests.test_after_sales import _create_as, _fulfilled
from tests.test_fulfillment import _receipt, _waiting_po
from tests.test_purchase_returns import _create_pr, _received_po, _submit_approve
from tests.test_sales_orders import _create_tenant


def _pick_and_confirm_outbound(client: TestClient, header: dict[str, str], order_id: int) -> dict:
    listed = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": order_id},
        headers=header,
    )
    assert listed.status_code == 200, listed.text
    outbound_id = listed.json()["data"]["items"][0]["id"]
    detail = client.get(f"/api/v1/outbound-orders/{outbound_id}", headers=header).json()["data"]
    picked = client.post(
        f"/api/v1/outbound-orders/{outbound_id}/pick",
        json={
            "items": [
                {"id": row["id"], "picked_quantity": row["planned_quantity"]}
                for row in detail["items"]
            ]
        },
        headers=header,
    )
    assert picked.status_code == 200, picked.text
    confirmed = client.post(f"/api/v1/outbound-orders/{outbound_id}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()["data"]


def test_sales_forward_reserve_outbound_deliver(client: TestClient) -> None:
    ctx = bootstrap(client, "core-so@example.com", "CoreSO", "core-so")
    warehouse = ctx.warehouse()
    product = ctx.product("核心货", "CORE-SO")
    sku_id = product["skus"][0]["id"]
    inventory = ctx.initialize(warehouse["id"], sku_id, 100)
    customer = ctx.customer()
    carrier = ctx.carrier()

    order = ctx.create_sales_order(customer["id"], warehouse["id"], sku_id, 80)
    order_id = order["id"]
    assert client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=ctx.header).status_code == 200
    confirm = client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=ctx.header)
    assert confirm.status_code == 200, confirm.text
    reserved = ctx.get_inventory(inventory["id"])
    assert reserved["quantity"] == 100
    assert reserved["reserved_quantity"] == 80
    assert reserved["available_quantity"] == 20

    outbound = _pick_and_confirm_outbound(client, ctx.header, order_id)
    after_out = ctx.get_inventory(inventory["id"])
    assert after_out["quantity"] == 20
    assert after_out["reserved_quantity"] == 0
    assert after_out["available_quantity"] == 20

    shipment = client.post(
        "/api/v1/shipments",
        json={
            "outbound_order_id": outbound["id"],
            "carrier_id": carrier["id"],
            "tracking_no": "CORE-SF-001",
            "items": [
                {
                    "outbound_order_item_id": outbound["items"][0]["id"],
                    "quantity": outbound["items"][0]["outbound_quantity"],
                }
            ],
        },
        headers=ctx.header,
    )
    assert shipment.status_code == 200, shipment.text
    shipment_id = shipment.json()["data"]["id"]
    assert client.post(f"/api/v1/shipments/{shipment_id}/confirm", headers=ctx.header).status_code == 200
    delivered = client.post(f"/api/v1/shipments/{shipment_id}/deliver", json={}, headers=ctx.header)
    assert delivered.status_code == 200, delivered.text
    finished = ctx.get_order(order_id)
    assert finished["status"] == "COMPLETED"
    final_stock = ctx.get_inventory(inventory["id"])
    assert final_stock["quantity"] == 20
    assert final_stock["reserved_quantity"] == 0


def test_purchase_two_partial_receipts(client: TestClient) -> None:
    owner, _ = register_and_login(client, "core-po@example.com")
    tenant_id = _create_tenant(client, owner, "CorePO", "core-po")
    order = _waiting_po(client, owner, tenant_id, 100)
    sku_id = order["items"][0]["sku_id"]
    header = {"Authorization": f"Bearer {owner}", "X-Tenant-ID": str(tenant_id)}
    first = _receipt(client, owner, tenant_id, order, 60)
    assert first.status_code == 200, first.text
    confirmed_first = client.post(
        f"/api/v1/purchase-receipts/{first.json()['data']['id']}/confirm",
        headers=header,
    )
    assert confirmed_first.status_code == 200, confirmed_first.text
    listed = client.get(
        "/api/v1/inventory",
        params={"warehouse_id": order["warehouse_id"]},
        headers=header,
    ).json()["data"]["items"]
    row = next(item for item in listed if item["sku_id"] == sku_id)
    assert row["quantity"] == 60

    refreshed = client.get(f"/api/v1/purchase-orders/{order['id']}", headers=header).json()["data"]
    second = _receipt(client, owner, tenant_id, refreshed, 40)
    assert second.status_code == 200, second.text
    confirmed_second = client.post(
        f"/api/v1/purchase-receipts/{second.json()['data']['id']}/confirm",
        headers=header,
    )
    assert confirmed_second.status_code == 200, confirmed_second.text
    after = client.get(f"/api/v1/inventory/{row['id']}", headers=header).json()["data"]
    assert after["quantity"] == 100
    po = client.get(f"/api/v1/purchase-orders/{order['id']}", headers=header).json()["data"]
    assert po["status"] == "RECEIVED"
    assert po["items"][0]["received_quantity"] == 100


def test_after_sale_return_inbound_and_refund(client: TestClient) -> None:
    owner, _ = register_and_login(client, "core-as@example.com")
    tenant_id = _create_tenant(client, owner, "CoreAS", "core-as")
    data = _fulfilled(client, owner, tenant_id, qty=5, stock=100)
    sku_id = data["sku_ids"][0]
    inventory_id = data["inventories"][sku_id]
    before = client.get(f"/api/v1/inventory/{inventory_id}", headers=data["header"]).json()["data"]
    assert before["quantity"] == 95
    item = data["order"]["items"][0]
    created = _create_as(
        client,
        data,
        {
            "sales_order_id": data["order_id"],
            "type": "RETURN_AND_REFUND",
            "reason": "核心链路退货",
            "items": [
                {
                    "sales_order_item_id": item["id"],
                    "return_quantity": 5,
                    "requested_refund_amount": "50",
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    as_id = created.json()["data"]["id"]
    approved = client.post(
        f"/api/v1/after-sales/{as_id}/approve", json={}, headers=data["header"]
    ).json()["data"]
    return_id = approved["return_order_id"]
    line_id = client.get(
        f"/api/v1/return-orders/{return_id}", headers=data["header"]
    ).json()["data"]["items"][0]["id"]
    received = client.post(
        f"/api/v1/return-orders/{return_id}/receive",
        json={"items": [{"item_id": line_id, "received_quantity": 5, "condition": "GOOD"}]},
        headers=data["header"],
    )
    assert received.status_code == 200, received.text
    inbound = client.post(
        f"/api/v1/return-orders/{return_id}/confirm-inbound", headers=data["header"]
    )
    assert inbound.status_code == 200, inbound.text
    after = client.get(f"/api/v1/inventory/{inventory_id}", headers=data["header"]).json()["data"]
    assert after["quantity"] == before["quantity"] + 5
    refund = client.post(f"/api/v1/after-sales/{as_id}/refunds", json={}, headers=data["header"])
    assert refund.status_code == 200, refund.text
    confirm = client.post(
        f"/api/v1/refunds/{refund.json()['data']['id']}/confirm",
        json={},
        headers=data["header"],
    )
    assert confirm.status_code == 200, confirm.text
    done = client.get(f"/api/v1/after-sales/{as_id}", headers=data["header"]).json()["data"]
    assert done["status"] == "COMPLETED"
    order = client.get(
        f"/api/v1/sales-orders/{data['order_id']}", headers=data["header"]
    ).json()["data"]
    assert order["items"][0]["quantity"] == 5


def test_purchase_return_outbound_decreases_inventory(client: TestClient) -> None:
    owner, _ = register_and_login(client, "core-prt@example.com")
    tenant_id = _create_tenant(client, owner, "CorePRT", "core-prt")
    data = _received_po(client, owner, tenant_id, ordered=20, received=20)
    sku_id = data["order"]["items"][0]["sku_id"]
    listed = client.get(
        "/api/v1/inventory",
        params={"warehouse_id": data["warehouse_id"]},
        headers=data["header"],
    ).json()["data"]["items"]
    row = next(item for item in listed if item["sku_id"] == sku_id)
    qty_before = row["quantity"]
    item = data["order"]["items"][0]
    created = _create_pr(
        client,
        data,
        {
            "purchase_order_id": data["order_id"],
            "settlement_type": "NO_REFUND",
            "reason": "核心采购退货",
            "items": [{"purchase_order_item_id": item["id"], "requested_return_quantity": 8}],
        },
    )
    assert created.status_code == 200, created.text
    approved = _submit_approve(client, data, created.json()["data"]["id"])
    outbound = client.post(
        f"/api/v1/purchase-returns/{approved['id']}/outbounds",
        json={"items": [{"purchase_return_item_id": approved["items"][0]["id"], "quantity": 8}]},
        headers=data["header"],
    )
    assert outbound.status_code == 200, outbound.text
    confirmed = client.post(
        f"/api/v1/purchase-return-outbounds/{outbound.json()['data']['id']}/confirm",
        headers=data["header"],
    )
    assert confirmed.status_code == 200, confirmed.text
    after = client.get(f"/api/v1/inventory/{row['id']}", headers=data["header"]).json()["data"]
    assert after["quantity"] == qty_before - 8
    po = client.get(
        f"/api/v1/purchase-orders/{data['order_id']}", headers=data["header"]
    ).json()["data"]
    assert po["items"][0]["quantity"] == 20
    assert po["items"][0]["received_quantity"] == 20
    assert po["items"][0]["returned_quantity"] == 8


def test_csv_formula_injection_is_prefixed() -> None:
    assert _csv_cell("=1+1") == "'=1+1"
    assert _csv_cell("+cmd") == "'+cmd"
    assert _csv_cell("-1") == "'-1"
    assert _csv_cell("@SUM(A1)") == "'@SUM(A1)"
    assert _csv_cell("普通客户") == "普通客户"
    assert _csv_cell(12) == 12
