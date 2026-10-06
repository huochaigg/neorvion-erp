from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.repositories.inventory import InventoryRepository
from app.schemas.sales_order import SalesOrderCancel
from app.services.sales_order import SalesOrderService
from fastapi.testclient import TestClient

from tests.helpers.auth_api import auth_header, register_and_login


def _create_tenant(client: TestClient, token: str, name: str, code: str) -> int:
    response = client.post(
        "/api/v1/tenants",
        json={"name": name, "code": code},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _roles(client: TestClient, token: str, tenant_id: int) -> dict[str, dict]:
    response = client.get("/api/v1/roles", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()["data"]}


def _catalog(client: TestClient, token: str, tenant_id: int) -> dict[str, int]:
    response = client.get("/api/v1/permissions", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item["id"] for item in response.json()["data"]}


def _member_id(client: TestClient, token: str, tenant_id: int) -> tuple[int, int]:
    response = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return int(data["user_id"]), int(data["member_id"])


def _add_member(
    client: TestClient,
    owner_token: str,
    tenant_id: int,
    email: str,
    role_ids: list[int],
) -> str:
    member_token, _ = register_and_login(client, email)
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": email, "role_ids": role_ids},
        headers=auth_header(owner_token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return member_token


def _warehouse(client: TestClient, token: str, tenant_id: int, name: str) -> dict:
    response = client.post(
        "/api/v1/warehouses",
        json={"name": name, "type": "DOMESTIC"},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _product(client: TestClient, token: str, tenant_id: int, name: str, skus: list[dict]) -> dict:
    category = client.post(
        "/api/v1/product-categories",
        json={"name": f"{name}-类目"},
        headers=auth_header(token, tenant_id),
    )
    assert category.status_code == 200, category.text
    created = client.post(
        "/api/v1/products",
        json={"name": name, "category_id": category.json()["data"]["id"], "skus": skus},
        headers=auth_header(token, tenant_id),
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]


def _customer(
    client: TestClient,
    token: str,
    tenant_id: int,
    name: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        "name": name,
        "country_code": "CN",
        "city": "深圳",
        "address": "科技园 1 号",
        **(extra or {}),
    }
    response = client.post(
        "/api/v1/customers",
        json=payload,
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _initialize(
    client: TestClient,
    token: str,
    tenant_id: int,
    warehouse_id: int,
    sku_id: int,
    quantity: int,
):
    return client.post(
        "/api/v1/inventory/initialize",
        json={"warehouse_id": warehouse_id, "sku_id": sku_id, "quantity": quantity},
        headers=auth_header(token, tenant_id),
    )


def _order(
    client: TestClient,
    token: str,
    tenant_id: int,
    *,
    customer_id: int,
    warehouse_id: int,
    items: list[dict],
    extra: dict | None = None,
):
    payload = {
        "customer_id": customer_id,
        "warehouse_id": warehouse_id,
        "recipient_name": "John Smith",
        "address": "科技园 1 号",
        "items": items,
        **(extra or {}),
    }
    return client.post("/api/v1/sales-orders", json=payload, headers=auth_header(token, tenant_id))


def _inventory(client: TestClient, token: str, tenant_id: int, inventory_id: int) -> dict:
    response = client.get(
        f"/api/v1/inventory/{inventory_id}",
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_customer_code_unique_per_tenant_and_isolation(client: TestClient) -> None:
    owner, _ = register_and_login(client, "cus-code@example.com")
    tenant_id = _create_tenant(client, owner, "CusCode", "cus-code")
    created = _customer(client, owner, tenant_id, "John Smith")
    assert created["code"].startswith("CUS")
    assert len(created["code"]) == 13
    custom = _customer(client, owner, tenant_id, "Mary", {"code": "CUS-SZ-1"})
    assert custom["code"] == "CUS-SZ-1"
    dup = client.post(
        "/api/v1/customers",
        json={"name": "重复", "code": "CUS-SZ-1"},
        headers=auth_header(owner, tenant_id),
    )
    assert dup.status_code == 409
    other_owner, _ = register_and_login(client, "cus-code-b@example.com")
    other_tenant = _create_tenant(client, other_owner, "CusCodeB", "cus-code-b")
    other = _customer(client, other_owner, other_tenant, "John Smith", {"code": "CUS-SZ-1"})
    assert other["code"] == "CUS-SZ-1"
    hidden = client.get(
        f"/api/v1/customers/{created['id']}",
        headers=auth_header(other_owner, other_tenant),
    )
    assert hidden.status_code == 404


def test_disabled_customer_blocks_order_and_in_use_blocks_delete(client: TestClient) -> None:
    owner, _ = register_and_login(client, "cus-disable@example.com")
    tenant_id = _create_tenant(client, owner, "CusDisable", "cus-disable")
    customer = _customer(client, owner, tenant_id, "可停用")
    warehouse = _warehouse(client, owner, tenant_id, "深圳仓")
    product = _product(client, owner, tenant_id, "手机", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    disabled = client.patch(
        f"/api/v1/customers/{customer['id']}/status",
        json={"status": "DISABLED"},
        headers=auth_header(owner, tenant_id),
    )
    assert disabled.status_code == 200, disabled.text
    blocked = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    )
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "CUSTOMER_DISABLED"
    enabled = client.patch(
        f"/api/v1/customers/{customer['id']}/status",
        json={"status": "ACTIVE"},
        headers=auth_header(owner, tenant_id),
    )
    assert enabled.status_code == 200
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    )
    assert created.status_code == 200, created.text
    deleted = client.delete(
        f"/api/v1/customers/{customer['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert deleted.status_code == 400
    assert deleted.json()["data"]["error"] == "CUSTOMER_IN_USE"
    order_id = created.json()["data"]["id"]
    detail = client.get(
        f"/api/v1/sales-orders/{order_id}",
        headers=auth_header(owner, tenant_id),
    )
    assert detail.json()["data"]["customer_name"] == "可停用"


def test_draft_keeps_address_snapshot_without_inventory_change(client: TestClient) -> None:
    owner, _ = register_and_login(client, "so-draft@example.com")
    tenant_id = _create_tenant(client, owner, "SoDraft", "so-draft")
    customer = _customer(
        client,
        owner,
        tenant_id,
        "John Smith",
        {"phone": "13800000000", "address": "客户新地址"},
    )
    warehouse = _warehouse(client, owner, tenant_id, "深圳一号仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "耳机",
        [
            {"name": "黑", "spec_values": {"颜色": "黑"}},
            {"name": "白", "spec_values": {"颜色": "白"}},
        ],
    )
    sku_a = product["skus"][0]["id"]
    sku_b = product["skus"][1]["id"]
    stock = _initialize(client, owner, tenant_id, warehouse["id"], sku_a, 3)
    inventory_id = stock.json()["data"]["id"]
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[
            {"sku_id": sku_a, "quantity": 25, "unit_price": "10.50"},
            {"sku_id": sku_b, "quantity": 2, "unit_price": "3.00"},
        ],
        extra={
            "recipient_name": "下单收件人",
            "address": "下单时的地址",
            "recipient_phone": "13900000000",
        },
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["order_no"].startswith("SO")
    assert data["sku_count"] == 2
    assert data["total_quantity"] == 27
    assert data["recipient_name"] == "下单收件人"
    assert data["address"] == "下单时的地址"
    assert data["items"][0]["reserved_quantity"] == 0
    changed = client.patch(
        f"/api/v1/customers/{customer['id']}",
        json={"address": "客户后来改掉的地址"},
        headers=auth_header(owner, tenant_id),
    )
    assert changed.status_code == 200, changed.text
    again = client.get(
        f"/api/v1/sales-orders/{data['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert again.json()["data"]["address"] == "下单时的地址"
    current = _inventory(client, owner, tenant_id, inventory_id)
    assert current["quantity"] == 3
    assert current["reserved_quantity"] == 0


def test_create_rejects_duplicate_sku_and_other_tenant_resources(client: TestClient) -> None:
    owner, _ = register_and_login(client, "so-iso@example.com")
    tenant_id = _create_tenant(client, owner, "SoIso", "so-iso")
    customer = _customer(client, owner, tenant_id, "本租户客户")
    warehouse = _warehouse(client, owner, tenant_id, "本租户仓")
    product = _product(client, owner, tenant_id, "本租户货", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    duplicated = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}, {"sku_id": sku_id, "quantity": 2}],
    )
    assert duplicated.status_code == 422

    other_owner, _ = register_and_login(client, "so-iso-b@example.com")
    other_tenant = _create_tenant(client, other_owner, "SoIsoB", "so-iso-b")
    other_customer = _customer(client, other_owner, other_tenant, "别人的客户")
    other_warehouse = _warehouse(client, other_owner, other_tenant, "别人的仓")
    other_product = _product(
        client,
        other_owner,
        other_tenant,
        "别人的货",
        [{"name": "默认", "spec_values": {}}],
    )
    foreign_customer = _order(
        client,
        owner,
        tenant_id,
        customer_id=other_customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    )
    assert foreign_customer.status_code == 404
    foreign_warehouse = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=other_warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    )
    assert foreign_warehouse.status_code == 404
    foreign_sku = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": other_product["skus"][0]["id"], "quantity": 1}],
    )
    assert foreign_sku.status_code == 404
    created_id = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    ).json()["data"]["id"]
    hidden = client.get(
        f"/api/v1/sales-orders/{created_id}",
        headers=auth_header(other_owner, other_tenant),
    )
    assert hidden.status_code == 404


def test_order_and_items_roll_back_together(client: TestClient, monkeypatch) -> None:
    owner, _ = register_and_login(client, "so-rb@example.com")
    tenant_id = _create_tenant(client, owner, "SoRb", "so-rb")
    customer = _customer(client, owner, tenant_id, "回滚客户")
    warehouse = _warehouse(client, owner, tenant_id, "回滚仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "回滚货",
        [{"name": "A", "spec_values": {}}, {"name": "B", "spec_values": {}}],
    )

    original = SalesOrderService._insert_items

    def _boom(self, order_id, items, sku_map):  # type: ignore[no-untyped-def]
        if len(items) > 1:
            raise RuntimeError("item fail")
        return original(self, order_id, items, sku_map)

    monkeypatch.setattr(SalesOrderService, "_insert_items", _boom)
    try:
        failed = _order(
            client,
            owner,
            tenant_id,
            customer_id=customer["id"],
            warehouse_id=warehouse["id"],
            items=[
                {"sku_id": product["skus"][0]["id"], "quantity": 1},
                {"sku_id": product["skus"][1]["id"], "quantity": 1},
            ],
        )
        assert failed.status_code >= 500
    except RuntimeError:
        pass
    listed = client.get("/api/v1/sales-orders", headers=auth_header(owner, tenant_id))
    assert listed.json()["data"]["total"] == 0


def test_status_machine_submit_confirm_and_illegal_transition(client: TestClient) -> None:
    owner, _ = register_and_login(client, "so-state@example.com")
    tenant_id = _create_tenant(client, owner, "SoState", "so-state")
    customer = _customer(client, owner, tenant_id, "状态客户")
    warehouse = _warehouse(client, owner, tenant_id, "状态仓")
    product = _product(client, owner, tenant_id, "状态货", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    created = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 20)
    inventory_id = created.json()["data"]["id"]
    draft = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 4, "unit_price": "2.00"}],
    ).json()["data"]
    header = auth_header(owner, tenant_id)
    direct = client.post(f"/api/v1/sales-orders/{draft['id']}/confirm", headers=header)
    assert direct.status_code == 400
    assert direct.json()["data"]["error"] == "INVALID_SALES_ORDER_TRANSITION"
    edited = client.patch(
        f"/api/v1/sales-orders/{draft['id']}",
        json={
            "remark": "草稿可改",
            "items": [{"sku_id": sku_id, "quantity": 4, "unit_price": "2.00"}],
        },
        headers=header,
    )
    assert edited.status_code == 200, edited.text
    submitted = client.post(f"/api/v1/sales-orders/{draft['id']}/submit", headers=header)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "PENDING_CONFIRMATION"
    locked = client.patch(
        f"/api/v1/sales-orders/{draft['id']}",
        json={"remark": "不能再改"},
        headers=header,
    )
    assert locked.status_code == 400
    assert locked.json()["data"]["error"] == "SALES_ORDER_NOT_EDITABLE"
    confirmed = client.post(f"/api/v1/sales-orders/{draft['id']}/confirm", headers=header)
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()["data"]
    assert body["status"] == "WAITING_OUTBOUND"
    assert body["items"][0]["reserved_quantity"] == 4
    assert body["items"][0]["shipped_quantity"] == 0
    stock = _inventory(client, owner, tenant_id, inventory_id)
    assert stock["quantity"] == 20
    assert stock["reserved_quantity"] == 4
    assert stock["available_quantity"] == 16
    txs = client.get(
        "/api/v1/inventory/transactions",
        params={"type": "RESERVE", "sku_id": sku_id},
        headers=header,
    )
    assert txs.status_code == 200, txs.text
    reserve_tx = txs.json()["data"]["items"][0]
    assert reserve_tx["reference_type"] == "SALES_ORDER"
    assert reserve_tx["reference_id"] == draft["id"]
    assert reserve_tx["change_quantity"] == 0
    assert reserve_tx["after_quantity"] == 20
    assert reserve_tx["after_reserved_quantity"] == 4


def test_multi_sku_confirm_is_atomic_when_one_sku_is_short(client: TestClient) -> None:
    owner, _ = register_and_login(client, "so-atomic@example.com")
    tenant_id = _create_tenant(client, owner, "SoAtomic", "so-atomic")
    customer = _customer(client, owner, tenant_id, "原子客户")
    warehouse = _warehouse(client, owner, tenant_id, "原子仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "原子货",
        [
            {"sku_code": "SKU-A", "name": "A", "spec_values": {}},
            {"sku_code": "SKU-B", "name": "B", "spec_values": {}},
        ],
    )
    sku_a = product["skus"][0]["id"]
    sku_b = product["skus"][1]["id"]
    stock_a = _initialize(client, owner, tenant_id, warehouse["id"], sku_a, 100)
    stock_b = _initialize(client, owner, tenant_id, warehouse["id"], sku_b, 2)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 5}, {"sku_id": sku_b, "quantity": 8}],
    )
    order_id = created.json()["data"]["id"]
    header = auth_header(owner, tenant_id)
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    failed = client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    assert failed.status_code == 400
    assert failed.json()["data"]["error"] == "INSUFFICIENT_AVAILABLE_INVENTORY"
    assert "SKU-B" in failed.json()["message"]
    detail = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    assert detail["status"] == "PENDING_CONFIRMATION"
    assert {item["reserved_quantity"] for item in detail["items"]} == {0}
    reserved_a = _inventory(client, owner, tenant_id, stock_a.json()["data"]["id"])
    reserved_b = _inventory(client, owner, tenant_id, stock_b.json()["data"]["id"])
    assert reserved_a["reserved_quantity"] == 0
    assert reserved_b["reserved_quantity"] == 0
    txs = client.get("/api/v1/inventory/transactions", params={"type": "RESERVE"}, headers=header)
    assert txs.json()["data"]["total"] == 0


def test_cancel_waiting_outbound_releases_once(client: TestClient) -> None:
    owner, _ = register_and_login(client, "so-cancel@example.com")
    tenant_id = _create_tenant(client, owner, "SoCancel", "so-cancel")
    customer = _customer(client, owner, tenant_id, "取消客户")
    warehouse = _warehouse(client, owner, tenant_id, "取消仓")
    product = _product(client, owner, tenant_id, "取消货", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    stock = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 30)
    inventory_id = stock.json()["data"]["id"]
    header = auth_header(owner, tenant_id)
    draft = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 6}],
    ).json()["data"]
    pending_cancel = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    ).json()["data"]
    client.post(f"/api/v1/sales-orders/{pending_cancel['id']}/submit", headers=header)
    cancelled_pending = client.post(
        f"/api/v1/sales-orders/{pending_cancel['id']}/cancel",
        json={"reason": "待确认取消"},
        headers=header,
    )
    assert cancelled_pending.status_code == 200, cancelled_pending.text
    assert _inventory(client, owner, tenant_id, inventory_id)["reserved_quantity"] == 0
    draft_cancel = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    ).json()["data"]
    cancelled_draft = client.post(
        f"/api/v1/sales-orders/{draft_cancel['id']}/cancel",
        json={"reason": "草稿取消"},
        headers=header,
    )
    assert cancelled_draft.json()["data"]["status"] == "CANCELLED"
    client.post(f"/api/v1/sales-orders/{draft['id']}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{draft['id']}/confirm", headers=header)
    cancelled = client.post(
        f"/api/v1/sales-orders/{draft['id']}/cancel",
        json={"reason": "客户不要了"},
        headers=header,
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()["data"]
    assert body["status"] == "CANCELLED"
    assert body["items"][0]["reserved_quantity"] == 0
    assert body["cancel_reason"] == "客户不要了"
    stock_after = _inventory(client, owner, tenant_id, inventory_id)
    assert stock_after["quantity"] == 30
    assert stock_after["reserved_quantity"] == 0
    release = client.get(
        "/api/v1/inventory/transactions",
        params={"type": "RELEASE", "sku_id": sku_id},
        headers=header,
    )
    release_tx = release.json()["data"]["items"][0]
    assert release_tx["reference_type"] == "SALES_ORDER"
    assert release_tx["reference_id"] == draft["id"]
    again = client.post(
        f"/api/v1/sales-orders/{draft['id']}/cancel",
        json={"reason": "再取消一次"},
        headers=header,
    )
    assert again.status_code == 400
    assert again.json()["data"]["error"] == "ORDER_ALREADY_CANCELLED"
    assert _inventory(client, owner, tenant_id, inventory_id)["reserved_quantity"] == 0
    reconfirm = client.post(f"/api/v1/sales-orders/{draft['id']}/confirm", headers=header)
    assert reconfirm.status_code == 400


def test_cancel_rolls_back_when_release_fails(client: TestClient, monkeypatch) -> None:
    owner, _ = register_and_login(client, "so-cancel-rb@example.com")
    tenant_id = _create_tenant(client, owner, "SoCancelRb", "so-cancel-rb")
    customer = _customer(client, owner, tenant_id, "释放失败客户")
    warehouse = _warehouse(client, owner, tenant_id, "释放失败仓")
    product = _product(
        client,
        owner,
        tenant_id,
        "释放失败货",
        [{"name": "A", "spec_values": {}}, {"name": "B", "spec_values": {}}],
    )
    sku_a = product["skus"][0]["id"]
    sku_b = product["skus"][1]["id"]
    stock_a = _initialize(client, owner, tenant_id, warehouse["id"], sku_a, 20)
    stock_b = _initialize(client, owner, tenant_id, warehouse["id"], sku_b, 20)
    header = auth_header(owner, tenant_id)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_a, "quantity": 5}, {"sku_id": sku_b, "quantity": 4}],
    )
    order_id = created.json()["data"]["id"]
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
    client.post(f"/api/v1/sales-orders/{order_id}/confirm", headers=header)
    calls = {"n": 0}
    original = InventoryRepository.release_if_reserved

    def _fail_second(self, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] >= 2:
            return 0
        return original(self, **kwargs)

    monkeypatch.setattr(InventoryRepository, "release_if_reserved", _fail_second)
    failed = client.post(
        f"/api/v1/sales-orders/{order_id}/cancel",
        json={"reason": "释放失败"},
        headers=header,
    )
    assert failed.status_code == 400
    detail = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    assert detail["status"] == "WAITING_OUTBOUND"
    assert {item["reserved_quantity"] for item in detail["items"]} == {5, 4}
    reserved_a = _inventory(client, owner, tenant_id, stock_a.json()["data"]["id"])
    reserved_b = _inventory(client, owner, tenant_id, stock_b.json()["data"]["id"])
    assert reserved_a["reserved_quantity"] == 5
    assert reserved_b["reserved_quantity"] == 4


def test_concurrent_confirm_same_order_reserves_once(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "so-race@example.com")
    tenant_id = _create_tenant(client, owner, "SoRace", "so-race")
    _, member_id = _member_id(client, owner, tenant_id)
    customer = _customer(client, owner, tenant_id, "并发客户")
    warehouse = _warehouse(client, owner, tenant_id, "并发仓")
    product = _product(client, owner, tenant_id, "并发货", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    stock = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 10)
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 4}],
    )
    order_id = created.json()["data"]["id"]
    header = auth_header(owner, tenant_id)
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)

    def _confirm() -> str:
        session = SessionLocal()
        try:
            context = TenantContext(
                user_id=user_id,
                tenant_id=tenant_id,
                member_id=member_id,
                is_owner=True,
                role=MemberRole.OWNER.value,
            )
            SalesOrderService(session, context).confirm_order(order_id)
            return "ok"
        except AppError as exc:
            data = exc.data or {}
            return str(data.get("error", exc.code))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _confirm(), range(2)))
    assert results.count("ok") == 1
    detail = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    assert detail["status"] == "WAITING_OUTBOUND"
    assert detail["items"][0]["reserved_quantity"] == 4
    reserved = _inventory(client, owner, tenant_id, stock.json()["data"]["id"])
    assert reserved["reserved_quantity"] == 4


def test_two_orders_cannot_oversell_the_same_stock(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "so-oversell@example.com")
    tenant_id = _create_tenant(client, owner, "SoOver", "so-over")
    _, member_id = _member_id(client, owner, tenant_id)
    customer = _customer(client, owner, tenant_id, "竞争客户")
    warehouse = _warehouse(client, owner, tenant_id, "竞争仓")
    product = _product(client, owner, tenant_id, "竞争货", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    stock = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 10)
    header = auth_header(owner, tenant_id)
    order_ids = []
    for _ in range(2):
        created = _order(
            client,
            owner,
            tenant_id,
            customer_id=customer["id"],
            warehouse_id=warehouse["id"],
            items=[{"sku_id": sku_id, "quantity": 8}],
        )
        order_id = created.json()["data"]["id"]
        client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)
        order_ids.append(order_id)

    def _confirm(order_id: int) -> str:
        session = SessionLocal()
        try:
            context = TenantContext(
                user_id=user_id,
                tenant_id=tenant_id,
                member_id=member_id,
                is_owner=True,
                role=MemberRole.OWNER.value,
            )
            SalesOrderService(session, context).confirm_order(order_id)
            return "ok"
        except AppError as exc:
            data = exc.data or {}
            return str(data.get("error", exc.code))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_confirm, order_ids))
    assert results.count("ok") == 1
    assert "INSUFFICIENT_AVAILABLE_INVENTORY" in results
    current = _inventory(client, owner, tenant_id, stock.json()["data"]["id"])
    assert current["quantity"] == 10
    assert current["reserved_quantity"] == 8
    assert current["available_quantity"] == 2


def test_confirm_and_cancel_race_stays_consistent(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "so-race2@example.com")
    tenant_id = _create_tenant(client, owner, "SoRace2", "so-race2")
    _, member_id = _member_id(client, owner, tenant_id)
    customer = _customer(client, owner, tenant_id, "竞态客户")
    warehouse = _warehouse(client, owner, tenant_id, "竞态仓")
    product = _product(client, owner, tenant_id, "竞态货", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    stock = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 15)
    inventory_id = stock.json()["data"]["id"]
    created = _order(
        client,
        owner,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 5}],
    )
    order_id = created.json()["data"]["id"]
    header = auth_header(owner, tenant_id)
    client.post(f"/api/v1/sales-orders/{order_id}/submit", headers=header)

    def _run(action: str) -> str:
        session = SessionLocal()
        try:
            context = TenantContext(
                user_id=user_id,
                tenant_id=tenant_id,
                member_id=member_id,
                is_owner=True,
                role=MemberRole.OWNER.value,
            )
            service = SalesOrderService(session, context)
            if action == "confirm":
                service.confirm_order(order_id)
            else:
                service.cancel_order(order_id, SalesOrderCancel(reason="并发取消"))
            return "ok"
        except AppError as exc:
            data = exc.data or {}
            return str(data.get("error", exc.code))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(_run, ["confirm", "cancel"]))
    detail = client.get(f"/api/v1/sales-orders/{order_id}", headers=header).json()["data"]
    reserved = _inventory(client, owner, tenant_id, inventory_id)["reserved_quantity"]
    item_reserved = detail["items"][0]["reserved_quantity"]
    if detail["status"] == "CANCELLED":
        assert item_reserved == 0
        assert reserved == 0
    elif detail["status"] == "WAITING_OUTBOUND":
        assert item_reserved == 5
        assert reserved == 5
    else:
        raise AssertionError(detail["status"])


def test_sales_order_and_customer_permissions(client: TestClient) -> None:
    owner, _ = register_and_login(client, "so-perm-owner@example.com")
    tenant_id = _create_tenant(client, owner, "SoPerm", "so-perm")
    roles = _roles(client, owner, tenant_id)
    catalog = _catalog(client, owner, tenant_id)
    assert "order:update" in catalog
    assert "order:submit" in catalog
    assert "customer:read" in catalog
    operator = _add_member(
        client,
        owner,
        tenant_id,
        "so-operator@example.com",
        [roles["OPERATOR"]["id"]],
    )
    viewer = _add_member(client, owner, tenant_id, "so-viewer@example.com", [roles["VIEWER"]["id"]])
    customer = _customer(client, owner, tenant_id, "权限客户")
    warehouse = _warehouse(client, owner, tenant_id, "权限仓")
    product = _product(client, owner, tenant_id, "权限货", [{"name": "默认", "spec_values": {}}])
    sku_id = product["skus"][0]["id"]
    _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 10)
    denied = _order(
        client,
        viewer,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    )
    assert denied.status_code == 403
    created = _order(
        client,
        operator,
        tenant_id,
        customer_id=customer["id"],
        warehouse_id=warehouse["id"],
        items=[{"sku_id": sku_id, "quantity": 1}],
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["data"]["id"]
    submitted = client.post(
        f"/api/v1/sales-orders/{order_id}/submit",
        headers=auth_header(operator, tenant_id),
    )
    assert submitted.status_code == 200, submitted.text
    confirmed = client.post(
        f"/api/v1/sales-orders/{order_id}/confirm",
        headers=auth_header(operator, tenant_id),
    )
    assert confirmed.status_code == 403
    listed = client.get("/api/v1/sales-orders", headers=auth_header(viewer, tenant_id))
    assert listed.status_code == 200
    customer_create = client.post(
        "/api/v1/customers",
        json={"name": "运营不能建客户"},
        headers=auth_header(operator, tenant_id),
    )
    assert customer_create.status_code == 403
    owner_confirm = client.post(
        f"/api/v1/sales-orders/{order_id}/confirm",
        headers=auth_header(owner, tenant_id),
    )
    assert owner_confirm.status_code == 200, owner_confirm.text
