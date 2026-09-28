from __future__ import annotations

from app.core.permissions import LEGACY_MANAGE_EXPANSION, PERMISSION_CATALOG, PermissionCode
from app.db.session import SessionLocal
from app.models.rbac import RolePermission
from app.models.tenant import TenantMember
from app.models.user import User
from app.services.rbac import RoleService
from fastapi.testclient import TestClient
from sqlalchemy import select

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


def _walk_tree(nodes: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for node in nodes:
        rows.append(node)
        rows.extend(_walk_tree(node.get("children") or []))
    return rows


def test_member_enterprise_display_name_is_tenant_local(client: TestClient) -> None:
    owner_a, _a = register_and_login(client, "v235-name-a@example.com", "张三")
    owner_b, _b = register_and_login(client, "v235-name-b@example.com", "老板乙")
    member_token, member_user_id = register_and_login(client, "v235-name-user@example.com", "张三")
    tenant_a = _create_tenant(client, owner_a, "NameA", "v235-na")
    tenant_b = _create_tenant(client, owner_b, "NameB", "v235-nb")
    added_a = client.post(
        f"/api/v1/tenants/{tenant_a}/members",
        json={"email": "v235-name-user@example.com"},
        headers=auth_header(owner_a, tenant_a),
    )
    added_b = client.post(
        f"/api/v1/tenants/{tenant_b}/members",
        json={"email": "v235-name-user@example.com"},
        headers=auth_header(owner_b, tenant_b),
    )
    assert added_a.status_code == 200, added_a.text
    assert added_b.status_code == 200, added_b.text
    member_a = added_a.json()["data"]["id"]
    member_b = added_b.json()["data"]["id"]
    assert added_a.json()["data"]["display_name"] == "张三"
    patched = client.patch(
        f"/api/v1/tenants/{tenant_a}/members/{member_a}",
        json={"display_name": "张经理"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["display_name"] == "张经理"
    assert patched.json()["data"]["member_display_name"] == "张经理"
    assert patched.json()["data"]["user_display_name"] == "张三"
    other = client.get(
        f"/api/v1/tenants/{tenant_b}/members/{member_b}",
        headers=auth_header(owner_b, tenant_b),
    )
    assert other.json()["data"]["display_name"] == "张三"
    stolen = client.patch(
        f"/api/v1/tenants/{tenant_b}/members/{member_b}",
        json={"display_name": "越权"},
        headers=auth_header(owner_a, tenant_a),
    )
    assert stolen.status_code == 404
    session = SessionLocal()
    try:
        user = session.get(User, member_user_id)
        assert user is not None
        assert user.display_name == "张三"
        row_a = session.get(TenantMember, member_a)
        row_b = session.get(TenantMember, member_b)
        assert row_a is not None and row_a.display_name == "张经理"
        assert row_b is not None and row_b.display_name is None
    finally:
        session.close()
    assert member_token


def test_owner_display_name_can_change_but_not_roles(client: TestClient) -> None:
    owner, owner_id = register_and_login(client, "v235-own-name@example.com", "企业主")
    tenant_id = _create_tenant(client, owner, "OwnName", "v235-on")
    listed = client.get(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=auth_header(owner, tenant_id),
    )
    owner_member = next(
        item for item in listed.json()["data"]["items"] if item["user_id"] == owner_id
    )
    patched = client.patch(
        f"/api/v1/tenants/{tenant_id}/members/{owner_member['id']}",
        json={"display_name": "创始人"},
        headers=auth_header(owner, tenant_id),
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["display_name"] == "创始人"
    roles = _roles(client, owner, tenant_id)
    blocked = client.put(
        f"/api/v1/tenants/{tenant_id}/members/{owner_member['id']}/roles",
        json={"role_ids": [roles["VIEWER"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    assert blocked.status_code == 403


def test_custom_role_edit_delete_and_in_use(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "v235-role-owner@example.com")
    register_and_login(client, "v235-role-user@example.com")
    tenant_id = _create_tenant(client, owner, "RoleCo", "v235-role")
    created = client.post(
        "/api/v1/roles",
        json={"name": "值班", "code": "DUTY235", "permission_ids": []},
        headers=auth_header(owner, tenant_id),
    )
    assert created.status_code == 200, created.text
    role_id = created.json()["data"]["id"]
    patched = client.patch(
        f"/api/v1/roles/{role_id}",
        json={"name": "夜班", "description": "夜间值班"},
        headers=auth_header(owner, tenant_id),
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "夜班"
    assert patched.json()["data"]["code"] == "DUTY235"
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "v235-role-user@example.com", "role_ids": [role_id]},
        headers=auth_header(owner, tenant_id),
    )
    assert added.status_code == 200, added.text
    in_use = client.delete(f"/api/v1/roles/{role_id}", headers=auth_header(owner, tenant_id))
    assert in_use.status_code == 400
    assert in_use.json()["code"] == 40041
    assert in_use.json()["data"]["error"] == "ROLE_IN_USE"
    assert in_use.json()["data"]["member_count"] == 1
    member_id = added.json()["data"]["id"]
    roles = _roles(client, owner, tenant_id)
    client.put(
        f"/api/v1/tenants/{tenant_id}/members/{member_id}/roles",
        json={"role_ids": [roles["VIEWER"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    deleted = client.delete(f"/api/v1/roles/{role_id}", headers=auth_header(owner, tenant_id))
    assert deleted.status_code == 200
    system = client.delete(
        f"/api/v1/roles/{roles['ADMIN']['id']}",
        headers=auth_header(owner, tenant_id),
    )
    assert system.status_code == 400
    assert system.json()["code"] == 40040


def test_cannot_mutate_foreign_tenant_role(client: TestClient) -> None:
    alice, _a = register_and_login(client, "v235-fk-alice@example.com")
    bob, _b = register_and_login(client, "v235-fk-bob@example.com")
    alice_tenant = _create_tenant(client, alice, "FkA", "v235-fka")
    bob_tenant = _create_tenant(client, bob, "FkB", "v235-fkb")
    created = client.post(
        "/api/v1/roles",
        json={"name": "客服", "code": "CS235", "permission_ids": []},
        headers=auth_header(bob, bob_tenant),
    )
    role_id = created.json()["data"]["id"]
    patched = client.patch(
        f"/api/v1/roles/{role_id}",
        json={"name": "被改"},
        headers=auth_header(alice, alice_tenant),
    )
    assert patched.status_code == 404
    deleted = client.delete(f"/api/v1/roles/{role_id}", headers=auth_header(alice, alice_tenant))
    assert deleted.status_code == 404


def test_legacy_manage_expansion_and_permission_tree(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "v235-tree-owner@example.com")
    tenant_id = _create_tenant(client, owner, "TreeCo", "v235-tree")
    catalog = _catalog(client, owner, tenant_id)
    assert len(catalog) == len(PERMISSION_CATALOG)
    session = SessionLocal()
    try:
        service = RoleService(session)
        assert service.seed_permission_catalog() == 0
        roles = _roles(client, owner, tenant_id)
        viewer_id = roles["VIEWER"]["id"]
        manage_id = catalog[PermissionCode.TENANT_MEMBER_MANAGE]
        exists = session.scalars(
            select(RolePermission).where(
                RolePermission.role_id == viewer_id,
                RolePermission.permission_id == manage_id,
            )
        ).first()
        if exists is None:
            session.add(
                RolePermission(
                    tenant_id=tenant_id,
                    role_id=viewer_id,
                    permission_id=manage_id,
                )
            )
            session.commit()
        added = service.expand_legacy_manage_permissions()
        session.commit()
        owned = {
            row.permission_id
            for row in session.scalars(
                select(RolePermission).where(RolePermission.role_id == viewer_id)
            ).all()
        }
        for extra in LEGACY_MANAGE_EXPANSION[PermissionCode.TENANT_MEMBER_MANAGE]:
            assert catalog[extra] in owned
        assert manage_id in owned
        assert added >= 0
    finally:
        session.close()
    tree = client.get("/api/v1/permissions/tree", headers=auth_header(owner, tenant_id))
    assert tree.status_code == 200, tree.text
    nodes = _walk_tree(tree.json()["data"])
    assert any(item["type"] == "DIRECTORY" and item["permission_id"] is None for item in nodes)
    actions = [item for item in nodes if item["type"] == "ACTION"]
    assert {item["permission_code"] for item in actions} >= {
        PermissionCode.TENANT_MEMBER_READ,
        PermissionCode.TENANT_MEMBER_CREATE,
        PermissionCode.TENANT_ROLE_DELETE,
        PermissionCode.TENANT_PERMISSION_READ,
    }
    assert PermissionCode.TENANT_MEMBER_MANAGE not in {
        item["permission_code"] for item in actions
    }


def test_fine_grained_member_and_role_permissions(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "v235-fg-owner@example.com")
    member_token, _mid = register_and_login(client, "v235-fg-user@example.com")
    outsider, _oid2 = register_and_login(client, "v235-fg-out@example.com")
    tenant_id = _create_tenant(client, owner, "FgCo", "v235-fg")
    catalog = _catalog(client, owner, tenant_id)
    created = client.post(
        "/api/v1/roles",
        json={
            "name": "只读成员",
            "code": "MEMREAD",
            "permission_ids": [catalog[PermissionCode.TENANT_MEMBER_READ]],
        },
        headers=auth_header(owner, tenant_id),
    )
    role_id = created.json()["data"]["id"]
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "v235-fg-user@example.com", "role_ids": [role_id]},
        headers=auth_header(owner, tenant_id),
    )
    member_id = added.json()["data"]["id"]
    headers = auth_header(member_token, tenant_id)
    assert (
        client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            json={"email": "v235-fg-out@example.com"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/tenants/{tenant_id}/members/{member_id}",
            json={"display_name": "改名"},
            headers=headers,
        ).status_code
        == 403
    )
    roles = _roles(client, owner, tenant_id)
    assert (
        client.put(
            f"/api/v1/tenants/{tenant_id}/members/{member_id}/roles",
            json={"role_ids": [roles["VIEWER"]["id"]]},
            headers=headers,
        ).status_code
        == 403
    )
    custom = client.post(
        "/api/v1/roles",
        json={"name": "临时", "code": "TMPFG", "permission_ids": []},
        headers=auth_header(owner, tenant_id),
    )
    custom_id = custom.json()["data"]["id"]
    assert (
        client.delete(f"/api/v1/roles/{custom_id}", headers=headers).status_code == 403
    )
    assert (
        client.put(
            f"/api/v1/roles/{custom_id}/permissions",
            json={"permission_ids": [catalog[PermissionCode.TENANT_READ]]},
            headers=headers,
        ).status_code
        == 403
    )
    granted = client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={
            "permission_ids": [
                catalog[PermissionCode.TENANT_MEMBER_READ],
                catalog[PermissionCode.TENANT_MEMBER_CREATE],
            ]
        },
        headers=auth_header(owner, tenant_id),
    )
    assert granted.status_code == 200, granted.text
    allowed = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "nobody-v235@example.com"},
        headers=headers,
    )
    assert allowed.status_code == 404
    assert allowed.json()["code"] == 40411
    assert outsider
