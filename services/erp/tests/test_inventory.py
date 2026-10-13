from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.schemas.inventory import InventoryAdjust, InventoryQtyChange
from app.services.inventory import InventoryService
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


def _create_warehouse(client: TestClient, token: str, tenant_id: int, name: str) -> dict:
    response = client.post(
        "/api/v1/warehouses",
        json={"name": name, "type": "DOMESTIC"},
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _create_product(
    client: TestClient,
    token: str,
    tenant_id: int,
    name: str,
    sku_code: str,
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
            "skus": [{"sku_code": sku_code, "name": f"{name}-SKU", "spec_values": {"size": "42"}}],
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
    remark: str | None = None,
):
    return client.post(
        "/api/v1/inventory/initialize",
        json={
            "warehouse_id": warehouse_id,
            "sku_id": sku_id,
            "quantity": quantity,
            "remark": remark,
        },
        headers=auth_header(token, tenant_id),
    )


def test_initialize_inventory_success_and_zero(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "inv-init@example.com")
    tenant_id = _create_tenant(client, owner, "InvInit", "inv-init")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "手机", "SKU0000000001")
    sku_id = product["skus"][0]["id"]
    created = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 100, "期初")
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["quantity"] == 100
    assert data["reserved_quantity"] == 0
    assert data["available_quantity"] == 100
    assert data["version"] == 0
    assert data["warehouse_name"] == "深圳仓"
    assert data["sku_code"] == "SKU0000000001"

    zero_wh = _create_warehouse(client, owner, tenant_id, "广州仓")
    zero = _initialize(client, owner, tenant_id, zero_wh["id"], sku_id, 0)
    assert zero.status_code == 200, zero.text
    assert zero.json()["data"]["quantity"] == 0

    tx = client.get(
        f"/api/v1/inventory/{data['id']}/transactions",
        headers=auth_header(owner, tenant_id),
    )
    assert tx.status_code == 200, tx.text
    first = tx.json()["data"]["items"][0]
    assert first["type"] == "INITIALIZE"
    assert first["before_quantity"] == 0
    assert first["after_quantity"] == 100
    assert first["change_quantity"] == 100
    assert first["operator_user_id"] == user_id
    assert first["operator_name"] == "User"
    assert first["remark"] == "期初"

    detail = client.get(f"/api/v1/inventory/{data['id']}", headers=auth_header(owner, tenant_id))
    assert detail.status_code == 200, detail.text
    recent = detail.json()["data"]["recent_transactions"]
    assert recent[0]["type"] == "INITIALIZE"
    assert recent[0]["operator_user_id"] == user_id
    assert recent[0]["operator_name"] == "User"


def test_initialize_already_exists_and_cross_tenant(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "inv-iso-a@example.com")
    owner_b, _ = register_and_login(client, "inv-iso-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "InvA", "inv-iso-a")
    tenant_b = _create_tenant(client, owner_b, "InvB", "inv-iso-b")
    warehouse_a = _create_warehouse(client, owner_a, tenant_a, "A仓")
    warehouse_b = _create_warehouse(client, owner_b, tenant_b, "B仓")
    product_a = _create_product(client, owner_a, tenant_a, "A货", "SKU-A")
    product_b = _create_product(client, owner_b, tenant_b, "B货", "SKU-B")
    sku_a = product_a["skus"][0]["id"]
    sku_b = product_b["skus"][0]["id"]
    first = _initialize(client, owner_a, tenant_a, warehouse_a["id"], sku_a, 10)
    assert first.status_code == 200, first.text
    dup = _initialize(client, owner_a, tenant_a, warehouse_a["id"], sku_a, 20)
    assert dup.status_code == 409
    assert dup.json()["data"]["error"] == "INVENTORY_ALREADY_EXISTS"

    stolen_sku = _initialize(client, owner_a, tenant_a, warehouse_a["id"], sku_b, 5)
    assert stolen_sku.status_code == 404
    stolen_wh = _initialize(client, owner_a, tenant_a, warehouse_b["id"], sku_a, 5)
    assert stolen_wh.status_code == 404

    listed_b = client.get("/api/v1/inventory", headers=auth_header(owner_b, tenant_b))
    assert listed_b.json()["data"]["items"] == []
    stolen_get = client.get(
        f"/api/v1/inventory/{first.json()['data']['id']}",
        headers=auth_header(owner_b, tenant_b),
    )
    assert stolen_get.status_code == 404


def test_adjust_in_out_and_insufficient_available(client: TestClient) -> None:
    owner, _ = register_and_login(client, "inv-adj@example.com")
    tenant_id = _create_tenant(client, owner, "InvAdj", "inv-adj")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "耳机", "SKU-HP")
    sku_id = product["skus"][0]["id"]
    created = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 100)
    inventory_id = created.json()["data"]["id"]

    added = client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        json={"type": "ADJUST_IN", "quantity": 20, "remark": "盘点补差"},
        headers=auth_header(owner, tenant_id),
    )
    assert added.status_code == 200, added.text
    assert added.json()["data"]["quantity"] == 120
    assert added.json()["data"]["available_quantity"] == 120
    assert added.json()["data"]["version"] == 1

    reserved = client.post(
        f"/api/v1/inventory/{inventory_id}/reserve",
        json={"quantity": 30},
        headers=auth_header(owner, tenant_id),
    )
    assert reserved.status_code == 200, reserved.text
    assert reserved.json()["data"]["quantity"] == 120
    assert reserved.json()["data"]["reserved_quantity"] == 30
    assert reserved.json()["data"]["available_quantity"] == 90

    too_much = client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        json={"type": "ADJUST_OUT", "quantity": 91},
        headers=auth_header(owner, tenant_id),
    )
    assert too_much.status_code == 400
    assert too_much.json()["data"]["error"] == "INSUFFICIENT_AVAILABLE_INVENTORY"

    reduced = client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        json={"type": "ADJUST_OUT", "quantity": 10, "remark": "盘点纠正"},
        headers=auth_header(owner, tenant_id),
    )
    assert reduced.status_code == 200, reduced.text
    data = reduced.json()["data"]
    assert data["quantity"] == 110
    assert data["reserved_quantity"] == 30
    assert data["available_quantity"] == 80

    tx = client.get(
        f"/api/v1/inventory/{inventory_id}/transactions",
        headers=auth_header(owner, tenant_id),
    )
    types = [item["type"] for item in tx.json()["data"]["items"]]
    assert types[:3] == ["ADJUST_OUT", "RESERVE", "ADJUST_IN"]
    out_tx = tx.json()["data"]["items"][0]
    assert out_tx["before_quantity"] == 120
    assert out_tx["after_quantity"] == 110
    assert out_tx["change_quantity"] == -10


def test_initialize_rolls_back_when_ledger_fails(client: TestClient, monkeypatch) -> None:
    owner, _ = register_and_login(client, "inv-rb@example.com")
    tenant_id = _create_tenant(client, owner, "InvRb", "inv-rb")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "回滚货", "SKU-RB")
    sku_id = product["skus"][0]["id"]

    def _boom(_self: object, _row: object) -> None:
        raise RuntimeError("ledger fail")

    monkeypatch.setattr("app.services.inventory.InventoryTransactionRepository.add", _boom)
    try:
        created = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 50)
        assert created.status_code >= 500
    except RuntimeError:
        pass
    listed = client.get("/api/v1/inventory", headers=auth_header(owner, tenant_id))
    assert listed.json()["data"]["items"] == []


def test_reserve_release_deduct_and_guards(client: TestClient) -> None:
    owner, _ = register_and_login(client, "inv-rsv@example.com")
    tenant_id = _create_tenant(client, owner, "InvRsv", "inv-rsv")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "预占货", "SKU-RSV")
    sku_id = product["skus"][0]["id"]
    created = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 100)
    inventory_id = created.json()["data"]["id"]
    header = auth_header(owner, tenant_id)

    first = client.post(
        f"/api/v1/inventory/{inventory_id}/reserve",
        json={"quantity": 20},
        headers=header,
    )
    assert first.json()["data"]["reserved_quantity"] == 20
    second = client.post(
        f"/api/v1/inventory/{inventory_id}/reserve",
        json={"quantity": 30},
        headers=header,
    )
    assert second.json()["data"]["reserved_quantity"] == 50
    assert second.json()["data"]["quantity"] == 100
    assert second.json()["data"]["available_quantity"] == 50

    short = client.post(
        f"/api/v1/inventory/{inventory_id}/reserve",
        json={"quantity": 51},
        headers=header,
    )
    assert short.status_code == 400
    assert short.json()["data"]["error"] == "INSUFFICIENT_AVAILABLE_INVENTORY"

    released = client.post(
        f"/api/v1/inventory/{inventory_id}/release",
        json={"quantity": 10},
        headers=header,
    )
    assert released.json()["data"]["reserved_quantity"] == 40
    over_release = client.post(
        f"/api/v1/inventory/{inventory_id}/release",
        json={"quantity": 41},
        headers=header,
    )
    assert over_release.status_code == 400
    assert over_release.json()["data"]["error"] == "INSUFFICIENT_RESERVED_INVENTORY"
    current = client.get(f"/api/v1/inventory/{inventory_id}", headers=header)
    assert current.json()["data"]["reserved_quantity"] == 40

    deducted = client.post(
        f"/api/v1/inventory/{inventory_id}/deduct-reserved",
        json={"quantity": 10},
        headers=header,
    )
    assert deducted.status_code == 200, deducted.text
    data = deducted.json()["data"]
    assert data["quantity"] == 90
    assert data["reserved_quantity"] == 30
    short_deduct = client.post(
        f"/api/v1/inventory/{inventory_id}/deduct-reserved",
        json={"quantity": 31},
        headers=header,
    )
    assert short_deduct.status_code == 400


def test_ledger_immutable_http(client: TestClient) -> None:
    owner, _ = register_and_login(client, "inv-immut@example.com")
    tenant_id = _create_tenant(client, owner, "InvImm", "inv-imm")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "流水货", "SKU-TX")
    sku_id = product["skus"][0]["id"]
    created = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 5)
    inventory_id = created.json()["data"]["id"]
    header = auth_header(owner, tenant_id)
    assert client.patch(f"/api/v1/inventory/{inventory_id}", headers=header).status_code == 405
    assert client.delete(
        f"/api/v1/inventory/{inventory_id}/transactions",
        headers=header,
    ).status_code == 405
    tx = client.get("/api/v1/inventory/transactions", headers=header)
    assert tx.status_code == 200
    assert tx.json()["data"]["items"][0]["type"] == "INITIALIZE"


def test_inventory_list_search_and_pagination(client: TestClient) -> None:
    owner, _ = register_and_login(client, "inv-list@example.com")
    tenant_id = _create_tenant(client, owner, "InvList", "inv-list")
    sz = _create_warehouse(client, owner, tenant_id, "深圳仓")
    gz = _create_warehouse(client, owner, tenant_id, "广州仓")
    phone = _create_product(client, owner, tenant_id, "旗舰手机", "SKU-PHONE")
    cable = _create_product(client, owner, tenant_id, "数据线", "SKU-CABLE")
    _initialize(client, owner, tenant_id, sz["id"], phone["skus"][0]["id"], 8)
    _initialize(client, owner, tenant_id, gz["id"], cable["skus"][0]["id"], 0)
    header = auth_header(owner, tenant_id)

    by_sku = client.get("/api/v1/inventory", params={"sku_code": "PHONE"}, headers=header)
    assert [item["sku_code"] for item in by_sku.json()["data"]["items"]] == ["SKU-PHONE"]
    by_name = client.get("/api/v1/inventory", params={"q": "数据线"}, headers=header)
    assert [item["product_name"] for item in by_name.json()["data"]["items"]] == ["数据线"]
    by_wh = client.get("/api/v1/inventory", params={"warehouse_id": sz["id"]}, headers=header)
    assert [item["warehouse_name"] for item in by_wh.json()["data"]["items"]] == ["深圳仓"]
    zero = client.get("/api/v1/inventory", params={"stock_status": "ZERO"}, headers=header)
    assert [item["sku_code"] for item in zero.json()["data"]["items"]] == ["SKU-CABLE"]
    low = client.get(
        "/api/v1/inventory",
        params={"stock_status": "LOW", "threshold": 10},
        headers=header,
    )
    assert [item["sku_code"] for item in low.json()["data"]["items"]] == ["SKU-PHONE"]
    paged = client.get("/api/v1/inventory", params={"page": 1, "page_size": 1}, headers=header)
    assert paged.json()["data"]["total"] == 2
    assert len(paged.json()["data"]["items"]) == 1


def test_optimistic_lock_conflict(client: TestClient) -> None:
    owner, _ = register_and_login(client, "inv-opt@example.com")
    tenant_id = _create_tenant(client, owner, "InvOpt", "inv-opt")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "乐观货", "SKU-OPT")
    created = _initialize(client, owner, tenant_id, warehouse["id"], product["skus"][0]["id"], 100)
    inventory_id = created.json()["data"]["id"]
    header = auth_header(owner, tenant_id)
    first = client.post(
        f"/api/v1/inventory/{inventory_id}/optimistic-adjust",
        json={"expected_version": 0, "type": "ADJUST_IN", "quantity": 10},
        headers=header,
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["quantity"] == 110
    assert first.json()["data"]["version"] == 1
    conflict = client.post(
        f"/api/v1/inventory/{inventory_id}/optimistic-adjust",
        json={"expected_version": 0, "type": "ADJUST_IN", "quantity": 5},
        headers=header,
    )
    assert conflict.status_code == 400
    assert conflict.json()["data"]["error"] == "INVENTORY_CONFLICT"
    current = client.get(f"/api/v1/inventory/{inventory_id}", headers=header)
    assert current.json()["data"]["quantity"] == 110


def test_concurrent_reserve_does_not_oversell(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "inv-race@example.com")
    tenant_id = _create_tenant(client, owner, "InvRace", "inv-race")
    _, member_id = _member_id(client, owner, tenant_id)
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "竞态货", "SKU-RACE")
    created = _initialize(client, owner, tenant_id, warehouse["id"], product["skus"][0]["id"], 10)
    inventory_id = created.json()["data"]["id"]

    def _reserve() -> str:
        session = SessionLocal()
        try:
            context = TenantContext(
                user_id=user_id,
                tenant_id=tenant_id,
                member_id=member_id,
                is_owner=True,
                role=MemberRole.OWNER.value,
            )
            InventoryService(session, context).reserve_inventory(
                inventory_id,
                InventoryQtyChange(quantity=2),
            )
            return "ok"
        except AppError as exc:
            data = exc.data or {}
            return str(data.get("error", exc.code))
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _reserve(), range(8)))
    assert results.count("ok") == 5
    assert results.count("INSUFFICIENT_AVAILABLE_INVENTORY") == 3
    current = client.get(f"/api/v1/inventory/{inventory_id}", headers=auth_header(owner, tenant_id))
    data = current.json()["data"]
    assert data["quantity"] == 10
    assert data["reserved_quantity"] == 10
    assert data["available_quantity"] == 0


def test_concurrent_adjust_for_update(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "inv-lock@example.com")
    tenant_id = _create_tenant(client, owner, "InvLock", "inv-lock")
    _, member_id = _member_id(client, owner, tenant_id)
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "锁货", "SKU-LOCK")
    created = _initialize(client, owner, tenant_id, warehouse["id"], product["skus"][0]["id"], 100)
    inventory_id = created.json()["data"]["id"]

    def _adjust() -> None:
        session = SessionLocal()
        try:
            context = TenantContext(
                user_id=user_id,
                tenant_id=tenant_id,
                member_id=member_id,
                is_owner=True,
                role=MemberRole.OWNER.value,
            )
            InventoryService(session, context).adjust_inventory(
                inventory_id,
                InventoryAdjust(type="ADJUST_IN", quantity=10),
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: _adjust(), range(2)))
    current = client.get(f"/api/v1/inventory/{inventory_id}", headers=auth_header(owner, tenant_id))
    assert current.json()["data"]["quantity"] == 120


def test_inventory_permissions_enforced(client: TestClient) -> None:
    owner, _ = register_and_login(client, "inv-perm-owner@example.com")
    tenant_id = _create_tenant(client, owner, "InvPerm", "inv-perm")
    catalog = _catalog(client, owner, tenant_id)
    roles = _roles(client, owner, tenant_id)
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    product = _create_product(client, owner, tenant_id, "权限货", "SKU-PERM")
    sku_id = product["skus"][0]["id"]
    created = _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 40)
    inventory_id = created.json()["data"]["id"]

    def _role(code: str, *perm_codes: str) -> int:
        created_role = client.post(
            "/api/v1/roles",
            json={
                "name": code,
                "code": code,
                "permission_ids": [catalog[item] for item in perm_codes],
            },
            headers=auth_header(owner, tenant_id),
        )
        assert created_role.status_code == 200, created_role.text
        return int(created_role.json()["data"]["id"])

    reader = _add_member(
        client,
        owner,
        tenant_id,
        "inv-perm-read@example.com",
        [_role("INVREAD", PermissionCode.INVENTORY_READ)],
    )
    initer = _add_member(
        client,
        owner,
        tenant_id,
        "inv-perm-init@example.com",
        [_role("INVINIT", PermissionCode.INVENTORY_READ, PermissionCode.INVENTORY_INITIALIZE)],
    )
    adjuster = _add_member(
        client,
        owner,
        tenant_id,
        "inv-perm-adj@example.com",
        [_role("INVADJ", PermissionCode.INVENTORY_READ, PermissionCode.INVENTORY_ADJUST)],
    )
    tx_reader = _add_member(
        client,
        owner,
        tenant_id,
        "inv-perm-tx@example.com",
        [_role("INVTX", PermissionCode.INVENTORY_TRANSACTION_READ)],
    )
    operator = _add_member(
        client,
        owner,
        tenant_id,
        "inv-perm-op@example.com",
        [roles["OPERATOR"]["id"]],
    )

    denied_list = client.get("/api/v1/inventory", headers=auth_header(tx_reader, tenant_id))
    assert denied_list.status_code == 403
    allowed_list = client.get("/api/v1/inventory", headers=auth_header(reader, tenant_id))
    assert allowed_list.status_code == 200

    extra_wh = _create_warehouse(client, owner, tenant_id, "第二仓")
    denied_init = _initialize(client, reader, tenant_id, extra_wh["id"], sku_id, 1)
    assert denied_init.status_code == 403
    allowed_init = _initialize(client, initer, tenant_id, extra_wh["id"], sku_id, 1)
    assert allowed_init.status_code == 200, allowed_init.text

    denied_adjust = client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        json={"type": "ADJUST_IN", "quantity": 1},
        headers=auth_header(reader, tenant_id),
    )
    assert denied_adjust.status_code == 403
    allowed_adjust = client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        json={"type": "ADJUST_IN", "quantity": 1},
        headers=auth_header(adjuster, tenant_id),
    )
    assert allowed_adjust.status_code == 200, allowed_adjust.text

    denied_tx = client.get("/api/v1/inventory/transactions", headers=auth_header(reader, tenant_id))
    assert denied_tx.status_code == 403
    allowed_tx = client.get(
        "/api/v1/inventory/transactions",
        headers=auth_header(tx_reader, tenant_id),
    )
    assert allowed_tx.status_code == 200

    op_init = _initialize(
        client,
        operator,
        tenant_id,
        _create_warehouse(client, owner, tenant_id, "运营仓")["id"],
        sku_id,
        1,
    )
    assert op_init.status_code == 403
    op_list = client.get("/api/v1/inventory", headers=auth_header(operator, tenant_id))
    assert op_list.status_code == 200
    op_tx = client.get("/api/v1/inventory/transactions", headers=auth_header(operator, tenant_id))
    assert op_tx.status_code == 200


def test_referenced_warehouse_and_sku_cannot_delete(client: TestClient) -> None:
    owner, _ = register_and_login(client, "inv-ref@example.com")
    tenant_id = _create_tenant(client, owner, "InvRef", "inv-ref")
    warehouse = _create_warehouse(client, owner, tenant_id, "深圳仓")
    extra = _create_warehouse(client, owner, tenant_id, "空仓")
    product = _create_product(client, owner, tenant_id, "引用货", "SKU-REF")
    sku_id = product["skus"][0]["id"]
    extra_sku = client.post(
        f"/api/v1/products/{product['id']}/skus",
        json={"sku_code": "SKU-REF-2", "name": "备用", "spec_values": {}},
        headers=auth_header(owner, tenant_id),
    )
    assert extra_sku.status_code == 200, extra_sku.text
    _initialize(client, owner, tenant_id, warehouse["id"], sku_id, 3)
    header = auth_header(owner, tenant_id)
    blocked_wh = client.delete(f"/api/v1/warehouses/{warehouse['id']}", headers=header)
    assert blocked_wh.status_code == 400
    assert blocked_wh.json()["data"]["error"] == "WAREHOUSE_IN_USE"
    removed_wh = client.delete(f"/api/v1/warehouses/{extra['id']}", headers=header)
    assert removed_wh.status_code == 200
    blocked_sku = client.delete(
        f"/api/v1/products/{product['id']}/skus/{sku_id}",
        headers=header,
    )
    assert blocked_sku.status_code == 400
    assert blocked_sku.json()["data"]["error"] == "SKU_IN_USE"


def test_sku_remote_search(client: TestClient) -> None:
    owner, _ = register_and_login(client, "inv-sku@example.com")
    tenant_id = _create_tenant(client, owner, "InvSku", "inv-sku")
    _create_product(client, owner, tenant_id, "搜索手机", "SKU-SEARCH")
    found = client.get(
        "/api/v1/product-skus",
        params={"q": "搜索"},
        headers=auth_header(owner, tenant_id),
    )
    assert found.status_code == 200, found.text
    assert found.json()["data"]["items"][0]["product_name"] == "搜索手机"
