from __future__ import annotations

import pytest
from app.core.permissions import PermissionCode
from app.db.session import SessionLocal
from app.models.rbac import MemberRoleGrant
from app.models.tenant import MemberStatus, TenantMember
from app.repositories.rbac import RoleRepository
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

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


def test_owner_can_add_member_by_email_with_roles(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mem-owner@example.com", "Owner")
    _member_token, _mid = register_and_login(client, "mem-added@example.com", "Added")
    tenant_id = _create_tenant(client, owner, "MemCo", "mem-add")
    roles = _roles(client, owner, tenant_id)
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={
            "email": "mem-added@example.com",
            "role_ids": [roles["OPERATOR"]["id"], roles["WAREHOUSE"]["id"]],
        },
        headers=auth_header(owner, tenant_id),
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["email"] == "mem-added@example.com"
    assert {item["code"] for item in data["roles"]} == {"OPERATOR", "WAREHOUSE"}
    listed = client.get(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=auth_header(owner, tenant_id),
    )
    emails = {item["email"] for item in listed.json()["data"]["items"]}
    assert "mem-added@example.com" in emails


def test_regular_member_cannot_add_member(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mem-reg-owner@example.com")
    member_token, member_id = register_and_login(client, "mem-reg-member@example.com")
    outsider_token, _oid2 = register_and_login(client, "mem-reg-out@example.com")
    tenant_id = _create_tenant(client, owner, "RegCo", "mem-reg")
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-reg-member@example.com"},
        headers=auth_header(owner, tenant_id),
    )
    assert added.status_code == 200, added.text
    forbidden = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-reg-out@example.com"},
        headers=auth_header(member_token, tenant_id),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == 40320
    assert member_id > 0
    assert outsider_token


def test_duplicate_member_is_rejected(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mem-dup-owner@example.com")
    register_and_login(client, "mem-dup-user@example.com")
    tenant_id = _create_tenant(client, owner, "DupMem", "mem-dup")
    first = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-dup-user@example.com"},
        headers=auth_header(owner, tenant_id),
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-dup-user@example.com"},
        headers=auth_header(owner, tenant_id),
    )
    assert second.status_code == 409
    assert second.json()["code"] == 40911


def test_unknown_email_cannot_join(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mem-miss-owner@example.com")
    tenant_id = _create_tenant(client, owner, "MissCo", "mem-miss")
    missing = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "nobody-registered@example.com"},
        headers=auth_header(owner, tenant_id),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 40411


def test_member_can_hold_multiple_roles_via_api(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mem-multi-owner@example.com")
    register_and_login(client, "mem-multi-user@example.com")
    tenant_id = _create_tenant(client, owner, "MultiRole", "mem-multi")
    roles = _roles(client, owner, tenant_id)
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-multi-user@example.com", "role_ids": [roles["VIEWER"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    member_id = created.json()["data"]["id"]
    updated = client.put(
        f"/api/v1/tenants/{tenant_id}/members/{member_id}/roles",
        json={"role_ids": [roles["OPERATOR"]["id"], roles["WAREHOUSE"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    assert updated.status_code == 200, updated.text
    codes = {item["code"] for item in updated.json()["data"]["roles"]}
    assert codes == {"OPERATOR", "WAREHOUSE"}
    detail = client.get(
        f"/api/v1/tenants/{tenant_id}/members/{member_id}/permissions",
        headers=auth_header(owner, tenant_id),
    )
    perm_codes = set(detail.json()["data"]["permission_codes"])
    assert PermissionCode.PRODUCT_CREATE in perm_codes
    assert PermissionCode.INVENTORY_INBOUND in perm_codes
    assert PermissionCode.TENANT_MEMBER_MANAGE not in perm_codes


def test_cannot_assign_foreign_tenant_role(client: TestClient) -> None:
    alice, _a = register_and_login(client, "mem-fk-alice@example.com")
    bob, _b = register_and_login(client, "mem-fk-bob@example.com")
    register_and_login(client, "mem-fk-user@example.com")
    alice_tenant = _create_tenant(client, alice, "FkA", "mem-fka")
    bob_tenant = _create_tenant(client, bob, "FkB", "mem-fkb")
    bob_admin = _roles(client, bob, bob_tenant)["ADMIN"]["id"]
    created = client.post(
        f"/api/v1/tenants/{alice_tenant}/members",
        json={"email": "mem-fk-user@example.com", "role_ids": [bob_admin]},
        headers=auth_header(alice, alice_tenant),
    )
    assert created.status_code == 404
    assert created.json()["code"] == 40420


def test_cannot_modify_foreign_tenant_member(client: TestClient) -> None:
    alice, _a = register_and_login(client, "mem-x-alice@example.com")
    bob, _b = register_and_login(client, "mem-x-bob@example.com")
    register_and_login(client, "mem-x-user@example.com")
    alice_tenant = _create_tenant(client, alice, "Xa", "mem-xa")
    bob_tenant = _create_tenant(client, bob, "Xb", "mem-xb")
    added = client.post(
        f"/api/v1/tenants/{bob_tenant}/members",
        json={"email": "mem-x-user@example.com"},
        headers=auth_header(bob, bob_tenant),
    )
    member_id = added.json()["data"]["id"]
    stolen = client.put(
        f"/api/v1/tenants/{bob_tenant}/members/{member_id}/roles",
        json={"role_ids": []},
        headers=auth_header(alice, alice_tenant),
    )
    assert stolen.status_code == 404
    assert stolen.json()["code"] == 40410
    detail = client.get(
        f"/api/v1/tenants/{bob_tenant}/members/{member_id}",
        headers=auth_header(alice, alice_tenant),
    )
    assert detail.status_code == 404


def test_cannot_grant_owner_via_member_api(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mem-own-owner@example.com")
    register_and_login(client, "mem-own-user@example.com")
    tenant_id = _create_tenant(client, owner, "OwnCo", "mem-own")
    owner_role = _roles(client, owner, tenant_id)["OWNER"]["id"]
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-own-user@example.com", "role_ids": [owner_role]},
        headers=auth_header(owner, tenant_id),
    )
    assert created.status_code == 403
    assert created.json()["code"] == 40321


def test_cannot_disable_last_owner(client: TestClient) -> None:
    owner, owner_id = register_and_login(client, "mem-last-owner@example.com")
    tenant_id = _create_tenant(client, owner, "LastMem", "mem-last")
    listed = client.get(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=auth_header(owner, tenant_id),
    )
    owner_member = next(
        item for item in listed.json()["data"]["items"] if item["user_id"] == owner_id
    )
    disabled = client.patch(
        f"/api/v1/tenants/{tenant_id}/members/{owner_member['id']}",
        json={"status": MemberStatus.DISABLED.value},
        headers=auth_header(owner, tenant_id),
    )
    assert disabled.status_code == 400
    assert disabled.json()["code"] == 40034
    roles = _roles(client, owner, tenant_id)
    mutate_owner = client.put(
        f"/api/v1/tenants/{tenant_id}/members/{owner_member['id']}/roles",
        json={"role_ids": [roles["ADMIN"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    assert mutate_owner.status_code == 403
    assert mutate_owner.json()["code"] == 40322


def test_replace_roles_rolls_back_on_error(client: TestClient, monkeypatch) -> None:
    owner, _oid = register_and_login(client, "mem-tx-owner@example.com")
    register_and_login(client, "mem-tx-user@example.com")
    tenant_id = _create_tenant(client, owner, "TxMem", "mem-tx")
    roles = _roles(client, owner, tenant_id)
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-tx-user@example.com", "role_ids": [roles["VIEWER"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    member_id = created.json()["data"]["id"]

    def explode(self, *, tenant_id: int, member_id: int, role_ids: list[int]) -> None:
        self.session.execute(
            delete(MemberRoleGrant).where(
                MemberRoleGrant.tenant_id == tenant_id,
                MemberRoleGrant.member_id == member_id,
            )
        )
        self.session.flush()
        raise RuntimeError("mid replace")

    monkeypatch.setattr(RoleRepository, "replace_member_roles", explode)
    with pytest.raises(RuntimeError, match="mid replace"):
        client.put(
            f"/api/v1/tenants/{tenant_id}/members/{member_id}/roles",
            json={"role_ids": [roles["OPERATOR"]["id"]]},
            headers=auth_header(owner, tenant_id),
        )
    detail = client.get(
        f"/api/v1/tenants/{tenant_id}/members/{member_id}",
        headers=auth_header(owner, tenant_id),
    )
    assert {item["code"] for item in detail.json()["data"]["roles"]} == {"VIEWER"}


def test_disabled_member_permission_stops_immediately(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mem-off-owner@example.com")
    member_token, _mid = register_and_login(client, "mem-off-user@example.com")
    tenant_id = _create_tenant(client, owner, "OffMem", "mem-off")
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-off-user@example.com"},
        headers=auth_header(owner, tenant_id),
    )
    member_id = created.json()["data"]["id"]
    patched = client.patch(
        f"/api/v1/tenants/{tenant_id}/members/{member_id}",
        json={"status": MemberStatus.DISABLED.value},
        headers=auth_header(owner, tenant_id),
    )
    assert patched.status_code == 200
    roles = client.get("/api/v1/roles", headers=auth_header(member_token, tenant_id))
    assert roles.status_code == 403
    assert roles.json()["code"] == 40310
    members = client.get(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=auth_header(member_token, tenant_id),
    )
    assert members.status_code == 403


def test_role_change_updates_effective_permissions(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mem-perm-owner@example.com")
    member_token, _mid = register_and_login(client, "mem-perm-user@example.com")
    tenant_id = _create_tenant(client, owner, "PermCo", "mem-perm")
    roles = _roles(client, owner, tenant_id)
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "mem-perm-user@example.com", "role_ids": [roles["VIEWER"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    member_id = created.json()["data"]["id"]
    before = client.get("/api/v1/tenants/current", headers=auth_header(member_token, tenant_id))
    assert PermissionCode.TENANT_MEMBER_MANAGE not in before.json()["data"]["permission_codes"]
    client.put(
        f"/api/v1/tenants/{tenant_id}/members/{member_id}/roles",
        json={"role_ids": [roles["ADMIN"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    after = client.get("/api/v1/tenants/current", headers=auth_header(member_token, tenant_id))
    assert PermissionCode.TENANT_MEMBER_MANAGE in after.json()["data"]["permission_codes"]
    session = SessionLocal()
    try:
        row = session.scalars(select(TenantMember).where(TenantMember.id == member_id)).one()
        assert row.role != "OWNER"
    finally:
        session.close()
