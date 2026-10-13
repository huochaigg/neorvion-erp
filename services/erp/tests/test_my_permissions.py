from __future__ import annotations

from app.core.permissions import PermissionCode
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


def _permissions_catalog(client: TestClient, token: str, tenant_id: int) -> dict[str, int]:
    response = client.get("/api/v1/permissions", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item["id"] for item in response.json()["data"]}


def test_current_member_permissions_query(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "perm-owner@example.com")
    tenant_id = _create_tenant(client, owner, "PermOwner", "perm-own")
    mine = client.get(
        "/api/v1/tenants/current/my-permissions",
        headers=auth_header(owner, tenant_id),
    )
    assert mine.status_code == 200, mine.text
    data = mine.json()["data"]
    assert "OWNER" in data["roles"]
    assert PermissionCode.TENANT_MEMBER_MANAGE in data["permissions"]
    assert PermissionCode.TENANT_ROLE_MANAGE in data["permissions"]


def test_multi_role_permissions_are_merged(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "perm-merge-owner@example.com")
    member_token, _mid = register_and_login(client, "perm-merge-user@example.com")
    tenant_id = _create_tenant(client, owner, "PermMerge", "perm-merge")
    roles = _roles(client, owner, tenant_id)
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={
            "email": "perm-merge-user@example.com",
            "role_ids": [roles["OPERATOR"]["id"], roles["WAREHOUSE"]["id"]],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert added.status_code == 200, added.text
    mine = client.get(
        "/api/v1/tenants/current/my-permissions",
        headers=auth_header(member_token, tenant_id),
    )
    data = mine.json()["data"]
    assert set(data["roles"]) == {"OPERATOR", "WAREHOUSE"}
    assert PermissionCode.PRODUCT_CREATE in data["permissions"]
    assert PermissionCode.INVENTORY_INBOUND in data["permissions"]
    assert PermissionCode.TENANT_MEMBER_MANAGE not in data["permissions"]


def test_tenant_a_permissions_not_used_for_tenant_b(client: TestClient) -> None:
    alice, _a = register_and_login(client, "perm-iso-alice@example.com")
    bob, _b = register_and_login(client, "perm-iso-bob@example.com")
    alice_tenant = _create_tenant(client, alice, "IsoA", "perm-iso-a")
    bob_tenant = _create_tenant(client, bob, "IsoB", "perm-iso-b")
    client.post(
        f"/api/v1/tenants/{bob_tenant}/members",
        json={"email": "perm-iso-alice@example.com"},
        headers=auth_header(bob, bob_tenant),
    )
    as_owner = client.get(
        "/api/v1/tenants/current/my-permissions",
        headers=auth_header(alice, alice_tenant),
    )
    as_viewer = client.get(
        "/api/v1/tenants/current/my-permissions",
        headers=auth_header(alice, bob_tenant),
    )
    assert PermissionCode.TENANT_MEMBER_MANAGE in as_owner.json()["data"]["permissions"]
    assert PermissionCode.TENANT_MEMBER_MANAGE not in as_viewer.json()["data"]["permissions"]
    assert as_viewer.json()["data"]["roles"] == ["VIEWER"]


def test_viewer_cannot_manage_members_or_roles_via_api(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "perm-deny-owner@example.com")
    member_token, _mid = register_and_login(client, "perm-deny-user@example.com")
    outsider, _oid2 = register_and_login(client, "perm-deny-out@example.com")
    tenant_id = _create_tenant(client, owner, "PermDeny", "perm-deny")
    client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "perm-deny-user@example.com"},
        headers=auth_header(owner, tenant_id),
    )
    members = client.get(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=auth_header(member_token, tenant_id),
    )
    assert members.status_code == 200
    add = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "perm-deny-out@example.com"},
        headers=auth_header(member_token, tenant_id),
    )
    assert add.status_code == 403
    assert add.json()["code"] == 40320
    roles = _roles(client, owner, tenant_id)
    mutate = client.patch(
        f"/api/v1/roles/{roles['VIEWER']['id']}",
        json={"name": "被篡改"},
        headers=auth_header(member_token, tenant_id),
    )
    assert mutate.status_code == 403
    assert mutate.json()["code"] == 40320
    assert outsider


def test_revoking_role_permission_takes_effect_immediately(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "perm-rev-owner@example.com")
    member_token, _mid = register_and_login(client, "perm-rev-user@example.com")
    tenant_id = _create_tenant(client, owner, "PermRev", "perm-rev")
    catalog = _permissions_catalog(client, owner, tenant_id)
    created = client.post(
        "/api/v1/roles",
        json={
            "name": "值班",
            "code": "DUTY",
            "permission_ids": [
                catalog[PermissionCode.TENANT_MEMBER_READ],
                catalog[PermissionCode.TENANT_MEMBER_MANAGE],
            ],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert created.status_code == 200, created.text
    duty_id = created.json()["data"]["id"]
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "perm-rev-user@example.com", "role_ids": [duty_id]},
        headers=auth_header(owner, tenant_id),
    )
    assert added.status_code == 200, added.text
    before = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "nobody-should-not-matter@example.com"},
        headers=auth_header(member_token, tenant_id),
    )
    assert before.status_code == 404
    assert before.json()["code"] == 40411
    stripped = client.put(
        f"/api/v1/roles/{duty_id}/permissions",
        json={"permission_ids": [catalog[PermissionCode.TENANT_READ]]},
        headers=auth_header(owner, tenant_id),
    )
    assert stripped.status_code == 200, stripped.text
    after = client.get(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=auth_header(member_token, tenant_id),
    )
    assert after.status_code == 403
    assert after.json()["code"] == 40320
    mine = client.get(
        "/api/v1/tenants/current/my-permissions",
        headers=auth_header(member_token, tenant_id),
    )
    assert PermissionCode.TENANT_MEMBER_MANAGE not in mine.json()["data"]["permissions"]
    assert PermissionCode.TENANT_MEMBER_READ not in mine.json()["data"]["permissions"]
