"""采购收货入库与销售出库。"""

from concurrent.futures import ThreadPoolExecutor

from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.services.outbound import OutboundOrderService
from app.services.purchase_receipt import PurchaseReceiptService
from fastapi.testclient import TestClient

from tests.helpers.auth_api import auth_header, register_and_login
from tests.test_purchase import (
    _create_po,
    _create_product,
    _create_supplier,
    _create_tenant,
    _create_warehouse,
)
from tests.test_sales_orders import (
    _customer,
    _initialize,
    _member_id,
    _order,
    _product,
    _warehouse,
)


def _approve(client: TestClient, token: str, tenant_id: int, order_id: int) -> dict:
    header = auth_header(token, tenant_id)
    submitted = client.post(f"/api/v1/purchase-orders/{order_id}/submit", headers=header)
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"/api/v1/purchase-orders/{order_id}/approve", headers=header)
    assert approved.status_code == 200, approved.text
    return approved.json()["data"]


def _waiting_po(client: TestClient, token: str, tenant_id: int, qty: int = 100) -> dict:
    supplier = _create_supplier(client, token, tenant_id, "收货供应商")
    warehouse = _create_warehouse(client, token, tenant_id, "收货仓")
    product = _create_product(
        client,
        token,
        tenant_id,
        "收货货",
        [{"sku_code": "RCV-A", "name": "A", "spec_values": {}}],
    )
    created = _create_po(
        client,
        token,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": product["skus"][0]["id"], "quantity": qty}],
    )
    assert created.status_code == 200, created.text
    order = _approve(client, token, tenant_id, created.json()["data"]["id"])
    return order


def _receipt(client: TestClient, token: str, tenant_id: int, order: dict, qty: int):
    item_id = order["items"][0]["id"]
    return client.post(
        "/api/v1/purchase-receipts",
        json={
            "purchase_order_id": order["id"],
            "items": [{"purchase_order_item_id": item_id, "received_quantity": qty}],
        },
        headers=auth_header(token, tenant_id),
    )


def test_draft_receipt_does_not_change_stock_and_full_receipt_inbounds(client: TestClient) -> None:
    owner, _ = register_and_login(client, "rcv-full@example.com")
    tenant_id = _create_tenant(client, owner, "RcvFull", "rcv-full")
    order = _waiting_po(client, owner, tenant_id, 10)
    sku_id = order["items"][0]["sku_id"]
    header = auth_header(owner, tenant_id)
    stock = _initialize(client, owner, tenant_id, order["warehouse_id"], sku_id, 100)
    inventory_id = stock.json()["data"]["id"]
    reserved_before = stock.json()["data"]["reserved_quantity"]
    draft = _receipt(client, owner, tenant_id, order, 10)
    assert draft.status_code == 200, draft.text
    assert draft.json()["data"]["status"] == "DRAFT"
    assert draft.json()["data"]["receipt_no"].startswith("PR")
    mid = client.get(f"/api/v1/inventory/{inventory_id}", headers=header)
    assert mid.json()["data"]["quantity"] == 100
    confirmed = client.post(
        f"/api/v1/purchase-receipts/{draft.json()['data']['id']}/confirm",
        headers=header,
    )
    assert confirmed.status_code == 200, confirmed.text
    again = client.post(
        f"/api/v1/purchase-receipts/{draft.json()['data']['id']}/confirm",
        headers=header,
    )
    assert again.status_code == 400
    assert again.json()["data"]["error"] == "PURCHASE_RECEIPT_ALREADY_CONFIRMED"
    after = client.get(f"/api/v1/inventory/{inventory_id}", headers=header).json()["data"]
    assert after["quantity"] == 110
    assert after["reserved_quantity"] == reserved_before
    po = client.get(f"/api/v1/purchase-orders/{order['id']}", headers=header).json()["data"]
    assert po["status"] == "RECEIVED"
    assert po["items"][0]["received_quantity"] == 10
    txs = client.get(
        "/api/v1/inventory/transactions",
        params={"type": "INBOUND"},
        headers=header,
    )
    row = txs.json()["data"]["items"][0]
    assert row["change_quantity"] == 10
    assert row["reference_type"] == "PURCHASE_RECEIPT"
    assert row["reference_id"] == draft.json()["data"]["id"]


def test_partial_receipts_reach_received_and_reject_overage(client: TestClient) -> None:
    owner, _ = register_and_login(client, "rcv-part@example.com")
    tenant_id = _create_tenant(client, owner, "RcvPart", "rcv-part")
    order = _waiting_po(client, owner, tenant_id, 100)
    header = auth_header(owner, tenant_id)
    first = _receipt(client, owner, tenant_id, order, 60)
    assert first.status_code == 200, first.text
    done = client.post(
        f"/api/v1/purchase-receipts/{first.json()['data']['id']}/confirm",
        headers=header,
    )
    assert done.status_code == 200, done.text
    po = client.get(f"/api/v1/purchase-orders/{order['id']}", headers=header).json()["data"]
    assert po["status"] == "PARTIALLY_RECEIVED"
    assert po["items"][0]["received_quantity"] == 60
    too_much = _receipt(client, owner, tenant_id, po, 50)
    assert too_much.status_code == 400
    second = _receipt(client, owner, tenant_id, po, 40)
    assert second.status_code == 200, second.text
    finished = client.post(
        f"/api/v1/purchase-receipts/{second.json()['data']['id']}/confirm",
        headers=header,
    )
    assert finished.status_code == 200, finished.text
    final = client.get(f"/api/v1/purchase-orders/{order['id']}", headers=header).json()["data"]
    assert final["status"] == "RECEIVED"
    assert final["items"][0]["received_quantity"] == 100


def test_receipt_creates_missing_inventory(client: TestClient) -> None:
    owner, _ = register_and_login(client, "rcv-new@example.com")
    tenant_id = _create_tenant(client, owner, "RcvNew", "rcv-new")
    order = _waiting_po(client, owner, tenant_id, 5)
    header = auth_header(owner, tenant_id)
    draft = _receipt(client, owner, tenant_id, order, 5)
    confirmed = client.post(
        f"/api/v1/purchase-receipts/{draft.json()['data']['id']}/confirm",
        headers=header,
    )
    assert confirmed.status_code == 200, confirmed.text
    listed = client.get(
        "/api/v1/inventory",
        params={"sku_id": order["items"][0]["sku_id"], "warehouse_id": order["warehouse_id"]},
        headers=header,
    )
    assert listed.status_code == 200, listed.text
    row = listed.json()["data"]["items"][0]
    assert row["quantity"] == 5
    assert row["reserved_quantity"] == 0


def test_two_receipts_cannot_over_receive(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "rcv-race@example.com")
    tenant_id = _create_tenant(client, owner, "RcvRace", "rcv-race")
    _, member_id = _member_id(client, owner, tenant_id)
    order = _waiting_po(client, owner, tenant_id, 100)
    header = auth_header(owner, tenant_id)
    first = _receipt(client, owner, tenant_id, order, 60).json()["data"]
    second = _receipt(client, owner, tenant_id, order, 60).json()["data"]

    def _confirm(receipt_id: int) -> str:
        session = SessionLocal()
        try:
            PurchaseReceiptService(
                session,
                TenantContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    member_id=member_id,
                    is_owner=True,
                    role=MemberRole.OWNER.value,
                ),
            ).confirm_receipt(receipt_id)
            return "ok"
        except AppError as exc:
            return str(exc.data.get("error", exc.code) if exc.data else exc.code)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_confirm, [first["id"], second["id"]]))
    assert results.count("ok") == 1
    po = client.get(f"/api/v1/purchase-orders/{order['id']}", headers=header).json()["data"]
    assert po["items"][0]["received_quantity"] == 60


def test_outbound_pick_does_not_change_stock_and_confirm_deducts(client: TestClient) -> None:
    owner, _ = register_and_login(client, "ob-full@example.com")
    tenant_id = _create_tenant(client, owner, "ObFull", "ob-full")
    customer = _customer(client, owner, tenant_id, "出库客户")
    warehouse = _warehouse(client, owner, tenant_id, "出库仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "出库货",
        [{"sku_code": "OUT-A", "name": "A", "spec_values": {"色": "黑"}}],
    )
    sku_id = product["skus"][0]["id"]
    stock = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 100)
    inventory_id = stock.json()["data"]["id"]
    header = auth_header(owner, tenant_id)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 10}],
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    confirmed = client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text
    listed = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": order_id},
        headers=header,
    )
    outbound = listed.json()["data"]["items"][0]
    assert outbound["outbound_no"].startswith("OUT")
    assert outbound["status"] == "PENDING_PICKING"
    still = client.get(f"/api/v1/inventory/{inventory_id}", headers=header).json()["data"]
    assert still["quantity"] == 100
    assert still["reserved_quantity"] == 10
    detail = client.get(f"/api/v1/outbound-orders/{outbound['id']}", headers=header).json()["data"]
    picked = client.post(
        f"/api/v1/outbound-orders/{outbound['id']}/pick",
        json={"items": [{"id": detail["items"][0]["id"], "picked_quantity": 6}]},
        headers=header,
    )
    assert picked.status_code == 200, picked.text
    after_pick = client.get(f"/api/v1/inventory/{inventory_id}", headers=header).json()["data"]
    assert after_pick["quantity"] == 100
    assert after_pick["reserved_quantity"] == 10
    shipped = client.post(f"/api/v1/outbound-orders/{outbound['id']}/confirm", headers=header)
    assert shipped.status_code == 200, shipped.text
    again = client.post(f"/api/v1/outbound-orders/{outbound['id']}/confirm", headers=header)
    assert again.status_code == 400
    assert again.json()["data"]["error"] == "OUTBOUND_ALREADY_CONFIRMED"
    final_stock = client.get(f"/api/v1/inventory/{inventory_id}", headers=header).json()["data"]
    assert final_stock["quantity"] == 94
    assert final_stock["reserved_quantity"] == 4
    assert final_stock["quantity"] - final_stock["reserved_quantity"] == 90
    sales = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    assert sales["status"] == "PARTIALLY_SHIPPED"
    assert sales["items"][0]["shipped_quantity"] == 6
    assert sales["items"][0]["reserved_quantity"] == 4
    txs = client.get(
        "/api/v1/inventory/transactions",
        params={"type": "OUTBOUND"},
        headers=header,
    ).json()["data"]["items"][0]
    assert txs["change_quantity"] == -6
    assert txs["reference_type"] == "OUTBOUND_ORDER"
    second = client.post(
        "/api/v1/outbound-orders",
        json={"sales_order_id": order_id},
        headers=header,
    )
    assert second.status_code == 200, second.text
    second_id = second.json()["data"]["id"]
    second_item = second.json()["data"]["items"][0]
    assert second_item["planned_quantity"] == 4
    client.post(
        f"/api/v1/outbound-orders/{second_id}/pick",
        json={"items": [{"id": second_item["id"], "picked_quantity": 4}]},
        headers=header,
    )
    done = client.post(f"/api/v1/outbound-orders/{second_id}/confirm", headers=header)
    assert done.status_code == 200, done.text
    finished = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    assert finished["status"] == "SHIPPED"
    assert finished["items"][0]["reserved_quantity"] == 0
    assert finished["items"][0]["shipped_quantity"] == 10
    blocked = client.post(
        f"/api/v1/sales-orders/{order_id}/cancel",
        json={"reason": "太晚"},
        headers=header,
    )
    assert blocked.status_code == 400


def test_repeated_picks_keep_each_quantity(client: TestClient) -> None:
    owner, _ = register_and_login(client, "ob-picks@example.com")
    tenant_id = _create_tenant(client, owner, "ObPicks", "ob-picks")
    customer = _customer(client, owner, tenant_id, "拣货客户")
    warehouse = _warehouse(client, owner, tenant_id, "拣货仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "拣货货",
        [{"sku_code": "PICK-A", "name": "A", "spec_values": {}}],
    )
    sku_id = product["skus"][0]["id"]
    _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 10)
    header = auth_header(owner, tenant_id)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 5}],
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    listed = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": order_id},
        headers=header,
    ).json()["data"]["items"][0]
    detail = client.get(f"/api/v1/outbound-orders/{listed['id']}", headers=header).json()["data"]
    item_id = detail["items"][0]["id"]
    first = client.post(
        f"/api/v1/outbound-orders/{listed['id']}/pick",
        json={"items": [{"id": item_id, "picked_quantity": 3}], "finish": False},
        headers=header,
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["status"] == "PENDING_PICKING"
    assert first.json()["data"]["items"][0]["picked_quantity"] == 3
    assert first.json()["data"]["picks"][0]["lines"][0]["quantity"] == 3
    assert first.json()["data"]["picks"][0]["lines"][0]["picked_before"] == 0
    assert first.json()["data"]["picks"][0]["lines"][0]["picked_after"] == 3
    stock = client.get("/api/v1/inventory", params={"sku_id": sku_id}, headers=header)
    assert stock.status_code == 200
    second = client.post(
        f"/api/v1/outbound-orders/{listed['id']}/pick",
        json={"items": [{"id": item_id, "picked_quantity": 2}], "finish": False},
        headers=header,
    )
    assert second.status_code == 200, second.text
    body = second.json()["data"]
    assert body["status"] == "PICKED"
    assert body["items"][0]["picked_quantity"] == 5
    assert [line["quantity"] for pick in body["picks"] for line in pick["lines"]] == [3, 2]
    assert body["picks"][1]["lines"][0]["picked_before"] == 3
    assert body["picks"][1]["lines"][0]["picked_after"] == 5
    sales = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    assert len(sales["picks"]) == 2
    assert sales["picks"][0]["picked_by_name"]
    too_much = client.post(
        f"/api/v1/outbound-orders/{listed['id']}/pick",
        json={"items": [{"id": item_id, "picked_quantity": 1}], "finish": False},
        headers=header,
    )
    assert too_much.status_code == 400


def test_same_outbound_confirm_only_succeeds_once(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "ob-race@example.com")
    tenant_id = _create_tenant(client, owner, "ObRace", "ob-race")
    _, member_id = _member_id(client, owner, tenant_id)
    customer = _customer(client, owner, tenant_id, "并发客户")
    warehouse = _warehouse(client, owner, tenant_id, "并发仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "并发货",
        [{"sku_code": "RACE-A", "name": "A", "spec_values": {}}],
    )
    sku_id = product["skus"][0]["id"]
    stock = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 20)
    inventory_id = stock.json()["data"]["id"]
    header = auth_header(owner, tenant_id)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 4}],
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    listed = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": order_id},
        headers=header,
    ).json()["data"]["items"][0]
    detail = client.get(f"/api/v1/outbound-orders/{listed['id']}", headers=header).json()["data"]
    picked = client.post(
        f"/api/v1/outbound-orders/{listed['id']}/pick",
        json={"items": [{"id": detail["items"][0]["id"], "picked_quantity": 4}]},
        headers=header,
    )
    assert picked.status_code == 200, picked.text

    def _confirm(_: int) -> str:
        session = SessionLocal()
        try:
            OutboundOrderService(
                session,
                TenantContext(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    member_id=member_id,
                    is_owner=True,
                    role=MemberRole.OWNER.value,
                ),
            ).confirm_outbound(listed["id"])
            return "ok"
        except AppError as exc:
            return str(exc.data.get("error", exc.code) if exc.data else exc.code)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_confirm, [1, 2]))
    assert results.count("ok") == 1
    final_stock = client.get(f"/api/v1/inventory/{inventory_id}", headers=header).json()["data"]
    assert final_stock["quantity"] == 16
    assert final_stock["reserved_quantity"] == 0


def test_receipt_multi_sku_failure_rolls_back(client: TestClient, monkeypatch) -> None:
    from app.services.inventory import InventoryService

    owner, _ = register_and_login(client, "rcv-atom@example.com")
    tenant_id = _create_tenant(client, owner, "RcvAtom", "rcv-atom")
    supplier = _create_supplier(client, owner, tenant_id, "原子供应商")
    warehouse = _create_warehouse(client, owner, tenant_id, "原子仓")
    product = _create_product(
        client,
        owner,
        tenant_id,
        "原子货",
        [
            {"sku_code": "ATOM-A", "name": "A", "spec_values": {}},
            {"sku_code": "ATOM-B", "name": "B", "spec_values": {}},
        ],
    )
    created = _create_po(
        client,
        owner,
        tenant_id,
        supplier_id=supplier["id"],
        warehouse_id=warehouse["id"],
        items=[
            {"sku_id": product["skus"][0]["id"], "quantity": 3},
            {"sku_id": product["skus"][1]["id"], "quantity": 4},
        ],
    )
    order = _approve(client, owner, tenant_id, created.json()["data"]["id"])
    header = auth_header(owner, tenant_id)
    receipt = client.post(
        "/api/v1/purchase-receipts",
        json={
            "purchase_order_id": order["id"],
            "items": [
                {"purchase_order_item_id": order["items"][0]["id"], "received_quantity": 3},
                {"purchase_order_item_id": order["items"][1]["id"], "received_quantity": 4},
            ],
        },
        headers=header,
    )
    assert receipt.status_code == 200, receipt.text
    receipt_id = receipt.json()["data"]["id"]
    original = InventoryService.inbound_within_transaction
    calls = {"n": 0}

    def _fail_second(self, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise AppError(message="第二行失败", status_code=400, data={"error": "FORCED"})
        return original(self, **kwargs)

    monkeypatch.setattr(InventoryService, "inbound_within_transaction", _fail_second)
    failed = client.post(f"/api/v1/purchase-receipts/{receipt_id}/confirm", headers=header)
    assert failed.status_code == 400
    still = client.get(f"/api/v1/purchase-receipts/{receipt_id}", headers=header).json()["data"]
    assert still["status"] == "DRAFT"
    po = client.get(f"/api/v1/purchase-orders/{order['id']}", headers=header).json()["data"]
    assert po["status"] == "WAITING_RECEIPT"
    assert all(item["received_quantity"] == 0 for item in po["items"])
    listed = client.get(
        "/api/v1/inventory",
        params={"warehouse_id": warehouse["id"]},
        headers=header,
    ).json()["data"]["items"]
    assert listed == []


def test_receipt_and_outbound_are_tenant_isolated(client: TestClient) -> None:
    owner, _ = register_and_login(client, "ff-iso@example.com")
    tenant_id = _create_tenant(client, owner, "FfIso", "ff-iso")
    order = _waiting_po(client, owner, tenant_id, 3)
    receipt = _receipt(client, owner, tenant_id, order, 3).json()["data"]
    other, _ = register_and_login(client, "ff-iso-b@example.com")
    other_tenant = _create_tenant(client, other, "FfIsoB", "ff-iso-b")
    hidden = client.get(
        f"/api/v1/purchase-receipts/{receipt['id']}",
        headers=auth_header(other, other_tenant),
    )
    assert hidden.status_code == 404
    foreign = client.post(
        "/api/v1/purchase-receipts",
        json={
            "purchase_order_id": order["id"],
            "items": [
                {
                    "purchase_order_item_id": order["items"][0]["id"],
                    "received_quantity": 1,
                }
            ],
        },
        headers=auth_header(other, other_tenant),
    )
    assert foreign.status_code == 404
    customer = _customer(client, owner, tenant_id, "隔离客户")
    sales_warehouse = _warehouse(client, owner, tenant_id, "隔离出库仓")
    sales_product = _product(
        client,
        owner,
        tenant_id,
        "隔离货",
        [{"sku_code": "ISO-A", "name": "A", "spec_values": {}}],
    )
    sku_id = sales_product["skus"][0]["id"]
    _initialize(client, owner, tenant_id, sales_warehouse["id"], sku_id, 8)
    header = auth_header(owner, tenant_id)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=sales_warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 2}],
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    outbound = client.get(
        "/api/v1/outbound-orders",
        params={"sales_order_id": order_id},
        headers=header,
    ).json()["data"]["items"][0]
    hidden_outbound = client.get(
        f"/api/v1/outbound-orders/{outbound['id']}",
        headers=auth_header(other, other_tenant),
    )
    assert hidden_outbound.status_code == 404
    foreign_outbound = client.post(
        "/api/v1/outbound-orders",
        json={"sales_order_id": order_id},
        headers=auth_header(other, other_tenant),
    )
    assert foreign_outbound.status_code == 404


def test_operator_cannot_confirm_receipt_or_outbound(client: TestClient) -> None:
    from tests.test_sales_orders import _add_member, _catalog, _roles

    owner, _ = register_and_login(client, "ff-perm@example.com")
    tenant_id = _create_tenant(client, owner, "FfPerm", "ff-perm")
    roles = _roles(client, owner, tenant_id)
    operator = _add_member(
        client,
        owner,
        tenant_id,
        "ff-op@example.com",
        [roles["OPERATOR"]["id"]],
    )
    order = _waiting_po(client, owner, tenant_id, 2)
    draft = _receipt(client, operator, tenant_id, order, 2)
    assert draft.status_code == 200, draft.text
    denied = client.post(
        f"/api/v1/purchase-receipts/{draft.json()['data']['id']}/confirm",
        headers=auth_header(operator, tenant_id),
    )
    assert denied.status_code == 403
    catalog = _catalog(client, owner, tenant_id)
    assert "purchase:receipt:confirm" in catalog
    assert "outbound:confirm" in catalog
