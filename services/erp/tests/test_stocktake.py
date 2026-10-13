from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.services.stocktake import StocktakeService
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


def _member_id(client: TestClient, token: str, tenant_id: int) -> tuple[int, int]:
    response = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return int(data["user_id"]), int(data["member_id"])


def _roles(client: TestClient, token: str, tenant_id: int) -> dict[str, dict]:
    response = client.get("/api/v1/roles", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()["data"]}


def _catalog(client: TestClient, token: str, tenant_id: int) -> dict[str, int]:
    response = client.get("/api/v1/permissions", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item["id"] for item in response.json()["data"]}


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


def _create_warehouse(client: TestClient, token: str, tenant_id: int, name: str) -> dict:
    response = client.post(
        "/api/v1/warehouses",
        json={"name": name, "type": "DOMESTIC"},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_product(
    client: TestClient, token: str, tenant_id: int, name: str, sku_code: str
) -> dict:
    category = client.post(
        "/api/v1/product-categories",
        json={"name": f"{name}-类目"},
        headers=auth_header(token, tenant_id),
    )
    assert category.status_code == 200, category.text
    created = client.post(
        "/api/v1/products",
        json={
            "name": name,
            "category_id": category.json()["data"]["id"],
            "skus": [{"sku_code": sku_code, "name": f"{name}-SKU"}],
        },
        headers=auth_header(token, tenant_id),
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]


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


def _headers(token: str, tenant_id: int) -> dict[str, str]:
    return auth_header(token, tenant_id)


def test_create_all_and_selected_sku_stocktake(client: TestClient) -> None:
    owner, _ = register_and_login(client, "st-create@example.com")
    tenant_id = _create_tenant(client, owner, "StCreate", "st-create")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product_a = _create_product(client, owner, tenant_id, "手机", "SKU-A")
    product_b = _create_product(client, owner, tenant_id, "耳机", "SKU-B")
    sku_a = product_a["skus"][0]["id"]
    sku_b = product_b["skus"][0]["id"]
    inv_a = _initialize(client, owner, tenant_id, warehouse["id"], sku_a, 100)
    _initialize(client, owner, tenant_id, warehouse["id"], sku_b, 40)
    all_st = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse["id"], "scope": "ALL"},
        headers=_headers(owner, tenant_id),
    )
    assert all_st.status_code == 200, all_st.text
    assert all_st.json()["data"]["status"] == "COUNTING"
    assert all_st.json()["data"]["stocktake_no"].startswith("ST")
    assert all_st.json()["data"]["sku_count"] == 2
    selected = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse["id"], "scope": "SELECTED_SKU", "sku_ids": [sku_a]},
        headers=_headers(owner, tenant_id),
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["data"]["sku_count"] == 1
    assert selected.json()["data"]["items"][0]["inventory_id"] == inv_a.json()["data"]["id"]
    assert selected.json()["data"]["items"][0]["system_quantity"] == 100


def test_count_difference_submit_and_lock_edit(client: TestClient) -> None:
    owner, _ = register_and_login(client, "st-count@example.com")
    tenant_id = _create_tenant(client, owner, "StCount", "st-count")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "手机", "SKU-C")
    sku_id = product["skus"][0]["id"]
    _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 100)
    created = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse["id"], "scope": "ALL"},
        headers=_headers(owner, tenant_id),
    )
    stocktake_id = created.json()["data"]["id"]
    item_id = created.json()["data"]["items"][0]["id"]
    incomplete = client.post(
        f"/api/v1/stocktakes/{stocktake_id}/submit",
        headers=_headers(owner, tenant_id),
    )
    assert incomplete.status_code == 400
    assert incomplete.json()["data"]["error"] == "STOCKTAKE_ITEMS_INCOMPLETE"
    saved = client.put(
        f"/api/v1/stocktakes/{stocktake_id}/items",
        json={"items": [{"item_id": item_id, "counted_quantity": 97, "remark": "少 3"}]},
        headers=_headers(owner, tenant_id),
    )
    assert saved.status_code == 200, saved.text
    item = saved.json()["data"]["items"][0]
    assert item["counted_quantity"] == 97
    assert item["difference_quantity"] == -3
    submitted = client.post(
        f"/api/v1/stocktakes/{stocktake_id}/submit",
        headers=_headers(owner, tenant_id),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "PENDING_CONFIRMATION"
    blocked = client.put(
        f"/api/v1/stocktakes/{stocktake_id}/items",
        json={"items": [{"item_id": item_id, "counted_quantity": 90}]},
        headers=_headers(owner, tenant_id),
    )
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "STOCKTAKE_NOT_EDITABLE"


def test_confirm_gain_loss_and_stocktake_transaction(client: TestClient) -> None:
    owner, _ = register_and_login(client, "st-gain@example.com")
    tenant_id = _create_tenant(client, owner, "StGain", "st-gain")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "手机", "SKU-D")
    sku_id = product["skus"][0]["id"]
    created_inv = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 100)
    inventory_id = created_inv.json()["data"]["id"]
    stocktake = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse["id"], "scope": "ALL"},
        headers=_headers(owner, tenant_id),
    ).json()["data"]
    item_id = stocktake["items"][0]["id"]
    client.put(
        f"/api/v1/stocktakes/{stocktake['id']}/items",
        json={"items": [{"item_id": item_id, "counted_quantity": 105}]},
        headers=_headers(owner, tenant_id),
    )
    client.post(f"/api/v1/stocktakes/{stocktake['id']}/submit", headers=_headers(owner, tenant_id))
    confirmed = client.post(
        f"/api/v1/stocktakes/{stocktake['id']}/confirm",
        headers=_headers(owner, tenant_id),
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["status"] == "CONFIRMED"
    current = client.get(f"/api/v1/inventory/{inventory_id}", headers=_headers(owner, tenant_id))
    assert current.json()["data"]["quantity"] == 105
    tx = client.get(
        f"/api/v1/inventory/{inventory_id}/transactions",
        headers=_headers(owner, tenant_id),
    )
    types = [row["type"] for row in tx.json()["data"]["items"]]
    assert "STOCKTAKE_ADJUSTMENT" in types
    adjustment = next(
        row for row in tx.json()["data"]["items"] if row["type"] == "STOCKTAKE_ADJUSTMENT"
    )
    assert adjustment["change_quantity"] == 5
    assert adjustment["reference_type"] == "STOCKTAKE"


def test_confirm_uses_difference_after_inbound(client: TestClient) -> None:
    owner, _ = register_and_login(client, "st-diff@example.com")
    tenant_id = _create_tenant(client, owner, "StDiff", "st-diff")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "手机", "SKU-E")
    sku_id = product["skus"][0]["id"]
    created_inv = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 100)
    inventory_id = created_inv.json()["data"]["id"]
    stocktake = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse["id"], "scope": "ALL"},
        headers=_headers(owner, tenant_id),
    ).json()["data"]
    item_id = stocktake["items"][0]["id"]
    inbound = client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        json={"type": "ADJUST_IN", "quantity": 20, "remark": "盘点期间入库"},
        headers=_headers(owner, tenant_id),
    )
    assert inbound.status_code == 200, inbound.text
    assert inbound.json()["data"]["quantity"] == 120
    client.put(
        f"/api/v1/stocktakes/{stocktake['id']}/items",
        json={"items": [{"item_id": item_id, "counted_quantity": 98}]},
        headers=_headers(owner, tenant_id),
    )
    client.post(f"/api/v1/stocktakes/{stocktake['id']}/submit", headers=_headers(owner, tenant_id))
    confirmed = client.post(
        f"/api/v1/stocktakes/{stocktake['id']}/confirm",
        headers=_headers(owner, tenant_id),
    )
    assert confirmed.status_code == 200, confirmed.text
    current = client.get(f"/api/v1/inventory/{inventory_id}", headers=_headers(owner, tenant_id))
    assert current.json()["data"]["quantity"] == 118


def test_confirm_rejects_below_reserved_and_rolls_back(client: TestClient) -> None:
    owner, _ = register_and_login(client, "st-rsv@example.com")
    tenant_id = _create_tenant(client, owner, "StRsv", "st-rsv")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product_a = _create_product(client, owner, tenant_id, "A货", "SKU-F1")
    product_b = _create_product(client, owner, tenant_id, "B货", "SKU-F2")
    sku_a = product_a["skus"][0]["id"]
    sku_b = product_b["skus"][0]["id"]
    inv_a = _initialize(client, owner, tenant_id, warehouse["id"], sku_a, 100).json()["data"]
    inv_b = _initialize(client, owner, tenant_id, warehouse["id"], sku_b, 50).json()["data"]
    reserved = client.post(
        f"/api/v1/inventory/{inv_a['id']}/reserve",
        json={"quantity": 30},
        headers=_headers(owner, tenant_id),
    )
    assert reserved.status_code == 200, reserved.text
    stocktake = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse["id"], "scope": "ALL"},
        headers=_headers(owner, tenant_id),
    ).json()["data"]
    items = {row["sku_id"]: row for row in stocktake["items"]}
    client.put(
        f"/api/v1/stocktakes/{stocktake['id']}/items",
        json={
            "items": [
                {"item_id": items[sku_a]["id"], "counted_quantity": 20},
                {"item_id": items[sku_b]["id"], "counted_quantity": 55},
            ]
        },
        headers=_headers(owner, tenant_id),
    )
    client.post(f"/api/v1/stocktakes/{stocktake['id']}/submit", headers=_headers(owner, tenant_id))
    failed = client.post(
        f"/api/v1/stocktakes/{stocktake['id']}/confirm",
        headers=_headers(owner, tenant_id),
    )
    assert failed.status_code == 400
    assert failed.json()["data"]["error"] == "STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY"
    after_a = client.get(f"/api/v1/inventory/{inv_a['id']}", headers=_headers(owner, tenant_id))
    after_b = client.get(f"/api/v1/inventory/{inv_b['id']}", headers=_headers(owner, tenant_id))
    assert after_a.json()["data"]["quantity"] == 100
    assert after_b.json()["data"]["quantity"] == 50


def test_repeat_and_concurrent_confirm_only_once(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "st-once@example.com")
    tenant_id = _create_tenant(client, owner, "StOnce", "st-once")
    _, member_id = _member_id(client, owner, tenant_id)
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "手机", "SKU-G")
    sku_id = product["skus"][0]["id"]
    created_inv = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 100)
    inventory_id = created_inv.json()["data"]["id"]
    stocktake = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse["id"], "scope": "ALL"},
        headers=_headers(owner, tenant_id),
    ).json()["data"]
    item_id = stocktake["items"][0]["id"]
    client.put(
        f"/api/v1/stocktakes/{stocktake['id']}/items",
        json={"items": [{"item_id": item_id, "counted_quantity": 90}]},
        headers=_headers(owner, tenant_id),
    )
    client.post(f"/api/v1/stocktakes/{stocktake['id']}/submit", headers=_headers(owner, tenant_id))
    first = client.post(
        f"/api/v1/stocktakes/{stocktake['id']}/confirm",
        headers=_headers(owner, tenant_id),
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/api/v1/stocktakes/{stocktake['id']}/confirm",
        headers=_headers(owner, tenant_id),
    )
    assert second.status_code == 400
    assert second.json()["data"]["error"] == "STOCKTAKE_ALREADY_CONFIRMED"
    assert client.get(
        f"/api/v1/inventory/{inventory_id}",
        headers=_headers(owner, tenant_id),
    ).json()["data"]["quantity"] == 90

    stocktake2 = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse["id"], "scope": "ALL"},
        headers=_headers(owner, tenant_id),
    ).json()["data"]
    item2 = stocktake2["items"][0]["id"]
    client.put(
        f"/api/v1/stocktakes/{stocktake2['id']}/items",
        json={"items": [{"item_id": item2, "counted_quantity": 88}]},
        headers=_headers(owner, tenant_id),
    )
    client.post(f"/api/v1/stocktakes/{stocktake2['id']}/submit", headers=_headers(owner, tenant_id))

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
            StocktakeService(session, context).confirm_stocktake(stocktake2["id"])
            return "ok"
        except AppError as exc:
            error = exc.data.get("error") if isinstance(exc.data, dict) else None
            return error or "err"
        except Exception:
            return "err"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _confirm(), range(2)))
    assert results.count("ok") == 1
    assert "STOCKTAKE_ALREADY_CONFIRMED" in results or results.count("err") == 1
    current = client.get(f"/api/v1/inventory/{inventory_id}", headers=_headers(owner, tenant_id))
    assert current.json()["data"]["quantity"] == 88


def test_stocktake_cross_tenant_and_permissions(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "st-a@example.com")
    owner_b, _ = register_and_login(client, "st-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "StA", "st-a")
    tenant_b = _create_tenant(client, owner_b, "StB", "st-b")
    warehouse_a = _create_warehouse(client, owner_a, tenant_a, "深圳仓")
    product = _create_product(client, owner_a, tenant_a, "手机", "SKU-H")
    sku_id = product["skus"][0]["id"]
    _initialize(client, owner_a, tenant_a, warehouse_a["id"], sku_id, 10)
    created = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse_a["id"], "scope": "ALL"},
        headers=_headers(owner_a, tenant_a),
    )
    stocktake_id = created.json()["data"]["id"]
    forbidden = client.get(
        f"/api/v1/stocktakes/{stocktake_id}",
        headers=_headers(owner_b, tenant_b),
    )
    assert forbidden.status_code == 404
    catalog = _catalog(client, owner_a, tenant_a)
    created_role = client.post(
        "/api/v1/roles",
        json={
            "name": "STREAD",
            "code": "STREAD",
            "permission_ids": [catalog[PermissionCode.STOCKTAKE_READ]],
        },
        headers=_headers(owner_a, tenant_a),
    )
    reader = _add_member(
        client,
        owner_a,
        tenant_a,
        "st-reader@example.com",
        [created_role.json()["data"]["id"]],
    )
    listed = client.get("/api/v1/stocktakes", headers=_headers(reader, tenant_a))
    assert listed.status_code == 200
    create_blocked = client.post(
        "/api/v1/stocktakes",
        json={"warehouse_id": warehouse_a["id"], "scope": "ALL"},
        headers=_headers(reader, tenant_a),
    )
    assert create_blocked.status_code == 403
    confirm_blocked = client.post(
        f"/api/v1/stocktakes/{stocktake_id}/confirm",
        headers=_headers(reader, tenant_a),
    )
    assert confirm_blocked.status_code == 403
