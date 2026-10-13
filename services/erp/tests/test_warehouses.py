from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.tenant import MemberRole
from app.services.warehouse import WarehouseService
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


def _create_warehouse(
    client: TestClient,
    token: str,
    tenant_id: int,
    name: str,
    **extra: object,
) -> dict:
    payload: dict[str, object] = {"name": name, "type": extra.pop("type", "DOMESTIC")}
    payload.update(extra)
    response = client.post(
        "/api/v1/warehouses",
        json=payload,
        headers=auth_header(token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_create_warehouse_auto_code_and_first_default(client: TestClient) -> None:
    owner, _ = register_and_login(client, "wh-create@example.com")
    tenant_id = _create_tenant(client, owner, "WhCreate", "wh-create")
    first = _create_warehouse(client, owner, tenant_id, "深圳一号仓")
    assert first["is_default"] is True
    assert first["status"] == "ACTIVE"
    assert first["code"] == f"WH{first['id']:010d}"
    assert first["type"] == "DOMESTIC"

    second = _create_warehouse(
        client,
        owner,
        tenant_id,
        "广州仓",
        code="GZ-01",
        type="OVERSEAS",
        country_code="cn",
        city="广州",
    )
    assert second["is_default"] is False
    assert second["code"] == "GZ-01"
    assert second["country_code"] == "CN"
    listed = client.get("/api/v1/warehouses", headers=auth_header(owner, tenant_id))
    defaults = [item for item in listed.json()["data"]["items"] if item["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == first["id"]


def test_warehouse_code_unique_per_tenant_only(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "wh-code-a@example.com")
    owner_b, _ = register_and_login(client, "wh-code-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "CodeA", "wh-code-a")
    tenant_b = _create_tenant(client, owner_b, "CodeB", "wh-code-b")
    _create_warehouse(client, owner_a, tenant_a, "仓A", code="SAME")
    dup = client.post(
        "/api/v1/warehouses",
        json={"name": "重复", "type": "DOMESTIC", "code": "same"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == 40940
    other = _create_warehouse(client, owner_b, tenant_b, "仓B", code="SAME")
    assert other["code"] == "SAME"


def test_warehouse_list_search_and_filters(client: TestClient) -> None:
    owner, _ = register_and_login(client, "wh-list@example.com")
    tenant_id = _create_tenant(client, owner, "ListCo", "wh-list")
    _create_warehouse(client, owner, tenant_id, "深圳仓", code="SZ01", type="DOMESTIC")
    overseas = _create_warehouse(
        client,
        owner,
        tenant_id,
        "洛杉矶仓",
        code="LA01",
        type="OVERSEAS",
        country_code="US",
        city="Los Angeles",
    )
    client.patch(
        f"/api/v1/warehouses/{overseas['id']}/status",
        json={"status": "DISABLED"},
        headers=auth_header(owner, tenant_id),
    )
    search = client.get(
        "/api/v1/warehouses",
        params={"q": "SZ01"},
        headers=auth_header(owner, tenant_id),
    )
    assert search.status_code == 200
    assert [item["code"] for item in search.json()["data"]["items"]] == ["SZ01"]
    typed = client.get(
        "/api/v1/warehouses",
        params={"type": "OVERSEAS"},
        headers=auth_header(owner, tenant_id),
    )
    assert [item["code"] for item in typed.json()["data"]["items"]] == ["LA01"]
    disabled = client.get(
        "/api/v1/warehouses",
        params={"status": "DISABLED"},
        headers=auth_header(owner, tenant_id),
    )
    assert [item["code"] for item in disabled.json()["data"]["items"]] == ["LA01"]
    paged = client.get(
        "/api/v1/warehouses",
        params={"page": 1, "page_size": 1},
        headers=auth_header(owner, tenant_id),
    )
    assert paged.json()["data"]["total"] == 2
    assert len(paged.json()["data"]["items"]) == 1


def test_warehouse_tenant_isolation(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "wh-iso-a@example.com")
    owner_b, _ = register_and_login(client, "wh-iso-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "IsoA", "wh-iso-a")
    tenant_b = _create_tenant(client, owner_b, "IsoB", "wh-iso-b")
    warehouse = _create_warehouse(client, owner_a, tenant_a, "A仓")
    listed = client.get("/api/v1/warehouses", headers=auth_header(owner_b, tenant_b))
    assert listed.json()["data"]["items"] == []
    stolen = client.get(
        f"/api/v1/warehouses/{warehouse['id']}",
        headers=auth_header(owner_b, tenant_b),
    )
    assert stolen.status_code == 404
    assert stolen.json()["code"] == 40440
    patched = client.patch(
        f"/api/v1/warehouses/{warehouse['id']}",
        json={"name": "偷改"},
        headers=auth_header(owner_b, tenant_b),
    )
    assert patched.status_code == 404
    defaulted = client.post(
        f"/api/v1/warehouses/{warehouse['id']}/set-default",
        headers=auth_header(owner_b, tenant_b),
    )
    assert defaulted.status_code == 404
    deleted = client.delete(
        f"/api/v1/warehouses/{warehouse['id']}",
        headers=auth_header(owner_b, tenant_b),
    )
    assert deleted.status_code == 404
    header_swap = client.get("/api/v1/warehouses", headers=auth_header(owner_b, tenant_a))
    assert header_swap.status_code in {403, 404}


def test_update_warehouse_keeps_code(client: TestClient) -> None:
    owner, _ = register_and_login(client, "wh-edit@example.com")
    tenant_id = _create_tenant(client, owner, "EditCo", "wh-edit")
    warehouse = _create_warehouse(client, owner, tenant_id, "原名")
    original_code = warehouse["code"]
    updated = client.patch(
        f"/api/v1/warehouses/{warehouse['id']}",
        json={
            "name": "新名",
            "address": "南山",
            "province": "广东",
            "city": "深圳",
            "contact_name": "张三",
            "contact_phone": "13800000000",
        },
        headers=auth_header(owner, tenant_id),
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["name"] == "新名"
    assert data["address"] == "南山"
    assert data["code"] == original_code
    assert data["is_default"] is True


def test_set_default_warehouse_and_cross_tenant(client: TestClient) -> None:
    owner_a, _ = register_and_login(client, "wh-def-a@example.com")
    owner_b, _ = register_and_login(client, "wh-def-b@example.com")
    tenant_a = _create_tenant(client, owner_a, "DefA", "wh-def-a")
    tenant_b = _create_tenant(client, owner_b, "DefB", "wh-def-b")
    first = _create_warehouse(client, owner_a, tenant_a, "仓A1")
    second = _create_warehouse(client, owner_a, tenant_a, "仓A2")
    other = _create_warehouse(client, owner_b, tenant_b, "仓B1")
    switched = client.post(
        f"/api/v1/warehouses/{second['id']}/set-default",
        headers=auth_header(owner_a, tenant_a),
    )
    assert switched.status_code == 200, switched.text
    listed = client.get("/api/v1/warehouses", headers=auth_header(owner_a, tenant_a))
    flags = {item["id"]: item["is_default"] for item in listed.json()["data"]["items"]}
    assert flags[second["id"]] is True
    assert flags[first["id"]] is False
    other_detail = client.get(
        f"/api/v1/warehouses/{other['id']}",
        headers=auth_header(owner_b, tenant_b),
    )
    assert other_detail.json()["data"]["is_default"] is True

    disabled = client.patch(
        f"/api/v1/warehouses/{first['id']}/status",
        json={"status": "DISABLED"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert disabled.status_code == 200
    refused = client.post(
        f"/api/v1/warehouses/{first['id']}/set-default",
        headers=auth_header(owner_a, tenant_a),
    )
    assert refused.status_code == 400
    assert refused.json()["data"]["error"] == "DISABLED_WAREHOUSE_CANNOT_SET_DEFAULT"


def test_concurrent_set_default_leaves_single_default(client: TestClient) -> None:
    owner, user_id = register_and_login(client, "wh-race@example.com")
    tenant_id = _create_tenant(client, owner, "RaceCo", "wh-race")
    _, member_id = _member_id(client, owner, tenant_id)
    first = _create_warehouse(client, owner, tenant_id, "竞态A")
    second = _create_warehouse(client, owner, tenant_id, "竞态B")

    def _set_default(warehouse_id: int) -> None:
        session = SessionLocal()
        try:
            context = TenantContext(
                user_id=user_id,
                tenant_id=tenant_id,
                member_id=member_id,
                is_owner=True,
                role=MemberRole.OWNER.value,
            )
            WarehouseService(session, context).set_default_warehouse(warehouse_id)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(_set_default, first["id"])
        future_b = pool.submit(_set_default, second["id"])
        future_a.result()
        future_b.result()

    listed = client.get("/api/v1/warehouses", headers=auth_header(owner, tenant_id))
    defaults = [item["id"] for item in listed.json()["data"]["items"] if item["is_default"]]
    assert len(defaults) == 1
    assert defaults[0] in {first["id"], second["id"]}


def test_warehouse_status_rules(client: TestClient) -> None:
    owner, _ = register_and_login(client, "wh-status@example.com")
    tenant_id = _create_tenant(client, owner, "StatusCo", "wh-status")
    default = _create_warehouse(client, owner, tenant_id, "默认仓")
    other = _create_warehouse(client, owner, tenant_id, "普通仓")
    blocked = client.patch(
        f"/api/v1/warehouses/{default['id']}/status",
        json={"status": "DISABLED"},
        headers=auth_header(owner, tenant_id),
    )
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "DEFAULT_WAREHOUSE_CANNOT_DISABLE"
    disabled = client.patch(
        f"/api/v1/warehouses/{other['id']}/status",
        json={"status": "DISABLED"},
        headers=auth_header(owner, tenant_id),
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "DISABLED"
    enabled = client.patch(
        f"/api/v1/warehouses/{other['id']}/status",
        json={"status": "ACTIVE"},
        headers=auth_header(owner, tenant_id),
    )
    assert enabled.json()["data"]["status"] == "ACTIVE"


def test_delete_warehouse_rules(client: TestClient) -> None:
    owner, _ = register_and_login(client, "wh-del@example.com")
    tenant_id = _create_tenant(client, owner, "DelCo", "wh-del")
    default = _create_warehouse(client, owner, tenant_id, "默认仓")
    extra = _create_warehouse(client, owner, tenant_id, "可删仓")
    blocked = client.delete(
        f"/api/v1/warehouses/{default['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert blocked.status_code == 400
    assert blocked.json()["data"]["error"] == "DEFAULT_WAREHOUSE_CANNOT_DELETE"
    removed = client.delete(
        f"/api/v1/warehouses/{extra['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert removed.status_code == 200
    last = client.delete(
        f"/api/v1/warehouses/{default['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert last.status_code == 200
    empty = client.get("/api/v1/warehouses", headers=auth_header(owner, tenant_id))
    assert empty.json()["data"]["items"] == []


def test_warehouse_permissions_enforced(client: TestClient) -> None:
    owner, _ = register_and_login(client, "wh-perm-owner@example.com")
    tenant_id = _create_tenant(client, owner, "PermWh", "wh-perm")
    catalog = _catalog(client, owner, tenant_id)

    def _role(code: str, *perm_codes: str) -> int:
        created = client.post(
            "/api/v1/roles",
            json={
                "name": code,
                "code": code,
                "permission_ids": [catalog[item] for item in perm_codes],
            },
            headers=auth_header(owner, tenant_id),
        )
        assert created.status_code == 200, created.text
        return int(created.json()["data"]["id"])

    none_token = _add_member(
        client,
        owner,
        tenant_id,
        "wh-perm-none@example.com",
        [_role("NONEWH")],
    )
    reader = _add_member(
        client,
        owner,
        tenant_id,
        "wh-perm-read@example.com",
        [_role("READWH", PermissionCode.WAREHOUSE_READ)],
    )
    creator = _add_member(
        client,
        owner,
        tenant_id,
        "wh-perm-create@example.com",
        [_role("CREATEWH", PermissionCode.WAREHOUSE_READ, PermissionCode.WAREHOUSE_CREATE)],
    )
    updater = _add_member(
        client,
        owner,
        tenant_id,
        "wh-perm-update@example.com",
        [_role("UPDATEWH", PermissionCode.WAREHOUSE_READ, PermissionCode.WAREHOUSE_UPDATE)],
    )
    disabler = _add_member(
        client,
        owner,
        tenant_id,
        "wh-perm-disable@example.com",
        [_role("DISABLEWH", PermissionCode.WAREHOUSE_READ, PermissionCode.WAREHOUSE_DISABLE)],
    )
    deleter = _add_member(
        client,
        owner,
        tenant_id,
        "wh-perm-delete@example.com",
        [_role("DELETEWH", PermissionCode.WAREHOUSE_READ, PermissionCode.WAREHOUSE_DELETE)],
    )

    denied_list = client.get("/api/v1/warehouses", headers=auth_header(none_token, tenant_id))
    assert denied_list.status_code == 403
    allowed_list = client.get("/api/v1/warehouses", headers=auth_header(reader, tenant_id))
    assert allowed_list.status_code == 200

    denied_create = client.post(
        "/api/v1/warehouses",
        json={"name": "无权限", "type": "DOMESTIC"},
        headers=auth_header(reader, tenant_id),
    )
    assert denied_create.status_code == 403
    created = client.post(
        "/api/v1/warehouses",
        json={"name": "可建仓", "type": "DOMESTIC"},
        headers=auth_header(creator, tenant_id),
    )
    assert created.status_code == 200, created.text
    warehouse_id = created.json()["data"]["id"]
    extra = _create_warehouse(client, owner, tenant_id, "第二仓")

    denied_update = client.patch(
        f"/api/v1/warehouses/{warehouse_id}",
        json={"name": "改不了"},
        headers=auth_header(reader, tenant_id),
    )
    assert denied_update.status_code == 403
    denied_default = client.post(
        f"/api/v1/warehouses/{extra['id']}/set-default",
        headers=auth_header(reader, tenant_id),
    )
    assert denied_default.status_code == 403
    updated = client.patch(
        f"/api/v1/warehouses/{warehouse_id}",
        json={"name": "已改名"},
        headers=auth_header(updater, tenant_id),
    )
    assert updated.status_code == 200
    set_default = client.post(
        f"/api/v1/warehouses/{extra['id']}/set-default",
        headers=auth_header(updater, tenant_id),
    )
    assert set_default.status_code == 200

    denied_disable = client.patch(
        f"/api/v1/warehouses/{warehouse_id}/status",
        json={"status": "DISABLED"},
        headers=auth_header(updater, tenant_id),
    )
    assert denied_disable.status_code == 403
    disabled = client.patch(
        f"/api/v1/warehouses/{warehouse_id}/status",
        json={"status": "DISABLED"},
        headers=auth_header(disabler, tenant_id),
    )
    assert disabled.status_code == 200

    denied_delete = client.delete(
        f"/api/v1/warehouses/{warehouse_id}",
        headers=auth_header(disabler, tenant_id),
    )
    assert denied_delete.status_code == 403
    deleted = client.delete(
        f"/api/v1/warehouses/{warehouse_id}",
        headers=auth_header(deleter, tenant_id),
    )
    assert deleted.status_code == 200


def test_warehouse_role_template_has_manage_without_delete(client: TestClient) -> None:
    owner, _ = register_and_login(client, "wh-role-owner@example.com")
    tenant_id = _create_tenant(client, owner, "RoleWh", "wh-role")
    roles = _roles(client, owner, tenant_id)
    warehouse_codes = {item["code"] for item in roles["WAREHOUSE"]["permissions"]}
    assert PermissionCode.WAREHOUSE_READ in warehouse_codes
    assert PermissionCode.WAREHOUSE_CREATE in warehouse_codes
    assert PermissionCode.WAREHOUSE_UPDATE in warehouse_codes
    assert PermissionCode.WAREHOUSE_DELETE not in warehouse_codes
    assert PermissionCode.WAREHOUSE_DISABLE not in warehouse_codes
    viewer_codes = {item["code"] for item in roles["VIEWER"]["permissions"]}
    assert PermissionCode.WAREHOUSE_READ in viewer_codes
    assert PermissionCode.WAREHOUSE_CREATE not in viewer_codes
    tree = client.get("/api/v1/permissions/tree", headers=auth_header(owner, tenant_id))
    assert tree.status_code == 200
    titles = []

    def _walk(nodes: list[dict]) -> None:
        for node in nodes:
            titles.append(node["title"])
            _walk(node.get("children") or [])

    _walk(tree.json()["data"])
    assert "仓库管理" in titles
    assert "设为默认" not in titles
