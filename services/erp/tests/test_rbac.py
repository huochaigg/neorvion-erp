from __future__ import annotations

import pytest
from app.core.exceptions import AppError
from app.core.permissions import (
    ADMIN_REQUIRED_PERMISSION_CODES,
    PERMISSION_CATALOG,
    PermissionCode,
    SystemRoleCode,
)
from app.db.session import SessionLocal
from app.models.rbac import MemberRoleGrant, RolePermission
from app.models.tenant import MemberRole, MemberStatus, TenantMember, TenantStatus
from app.repositories.rbac import RoleRepository
from app.services.authorization import AuthorizationService
from app.services.rbac import RoleService
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from tests.helpers.auth_api import auth_header, register_and_login


def _create_tenant(client: TestClient, token: str, name: str, code: str) -> int:
    response = client.post(
        "/api/v1/tenants",
        json={"name": name, "code": code},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _add_member(client: TestClient, owner_token: str, tenant_id: int, user_id: int) -> int:
    response = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"user_id": user_id},
        headers=auth_header(owner_token, tenant_id),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _role_map(client: TestClient, token: str, tenant_id: int) -> dict[str, dict]:
    response = client.get("/api/v1/roles", headers=auth_header(token, tenant_id))
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()["data"]}


def test_seed_permissions_is_idempotent() -> None:
    session = SessionLocal()
    try:
        service = RoleService(session)
        service.seed_permission_catalog()
        session.commit()
        count = session.execute(text("SELECT COUNT(*) FROM permissions")).scalar()
        assert count == len(PERMISSION_CATALOG)
        service.seed_permission_catalog()
        session.commit()
        again = session.execute(text("SELECT COUNT(*) FROM permissions")).scalar()
        assert again == count
    finally:
        session.close()


def test_create_tenant_bootstraps_default_roles_and_owner_grant(client: TestClient) -> None:
    token, user_id = register_and_login(client, "rbac-owner@example.com", "Owner")
    tenant_id = _create_tenant(client, token, "Acme", "rbac-acme")
    roles = _role_map(client, token, tenant_id)
    assert set(roles) == {item.value for item in SystemRoleCode}
    assert roles["OWNER"]["is_system"] is True
    owner_codes = {item["code"] for item in roles["OWNER"]["permissions"]}
    admin_codes = {item["code"] for item in roles["ADMIN"]["permissions"]}
    assert PermissionCode.TENANT_ROLE_MANAGE in owner_codes
    assert PermissionCode.TENANT_MEMBER_MANAGE in admin_codes
    assert PermissionCode.PRODUCT_READ in {item["code"] for item in roles["VIEWER"]["permissions"]}
    assert PermissionCode.TENANT_MEMBER_MANAGE not in {
        item["code"] for item in roles["VIEWER"]["permissions"]
    }

    session = SessionLocal()
    try:
        member = session.scalars(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == user_id,
            )
        ).one()
        grants = RoleRepository(session).list_grants_for_member(
            tenant_id=tenant_id,
            member_id=member.id,
        )
        assert {row.role.code for row in grants} == {SystemRoleCode.OWNER}
    finally:
        session.close()


def test_regular_member_has_no_manage_permission(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "rbac-mgr-owner@example.com")
    member_token, member_id = register_and_login(client, "rbac-mgr-member@example.com")
    tenant_id = _create_tenant(client, owner, "MgrCo", "rbac-mgr")
    _add_member(client, owner, tenant_id, member_id)
    forbidden = client.post(
        "/api/v1/roles",
        json={"name": "值班", "code": "DUTY", "permission_ids": []},
        headers=auth_header(member_token, tenant_id),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == 40320
    listed = client.get("/api/v1/roles", headers=auth_header(member_token, tenant_id))
    assert listed.status_code == 200


def test_member_can_hold_multiple_roles_and_permissions_merge(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "rbac-merge-owner@example.com")
    member_token, member_user_id = register_and_login(client, "rbac-merge-member@example.com")
    tenant_id = _create_tenant(client, owner, "MergeCo", "rbac-merge")
    member_row_id = _add_member(client, owner, tenant_id, member_user_id)
    roles = _role_map(client, owner, tenant_id)

    session = SessionLocal()
    try:
        service = RoleService(session)
        service.assign_member_role(
            tenant_id=tenant_id,
            member_id=member_row_id,
            role_id=roles["OPERATOR"]["id"],
            commit=True,
        )
        service.assign_member_role(
            tenant_id=tenant_id,
            member_id=member_row_id,
            role_id=roles["WAREHOUSE"]["id"],
            commit=True,
        )
        grants = RoleRepository(session).list_grants_for_member(
            tenant_id=tenant_id,
            member_id=member_row_id,
        )
        assert {row.role.code for row in grants} >= {
            SystemRoleCode.VIEWER,
            SystemRoleCode.OPERATOR,
            SystemRoleCode.WAREHOUSE,
        }
        context = AuthorizationService(session).build_context(
            user_id=member_user_id,
            tenant_id=tenant_id,
        )
        codes = AuthorizationService(session).permission_codes(context)
        assert PermissionCode.PRODUCT_CREATE in codes
        assert PermissionCode.INVENTORY_INBOUND in codes
        assert PermissionCode.TENANT_MEMBER_MANAGE not in codes
        assert PermissionCode.TENANT_ROLE_MANAGE not in codes
    finally:
        session.close()


def test_roles_are_isolated_between_tenants(client: TestClient) -> None:
    alice, _a = register_and_login(client, "rbac-alice@example.com", "Alice")
    bob, _b = register_and_login(client, "rbac-bob@example.com", "Bob")
    alice_tenant = _create_tenant(client, alice, "AliceCo", "rbac-alice")
    bob_tenant = _create_tenant(client, bob, "BobCo", "rbac-bob")
    alice_roles = _role_map(client, alice, alice_tenant)
    bob_roles = _role_map(client, bob, bob_tenant)
    assert alice_roles["ADMIN"]["id"] != bob_roles["ADMIN"]["id"]
    stolen = client.get(
        f"/api/v1/roles/{bob_roles['ADMIN']['id']}",
        headers=auth_header(alice, alice_tenant),
    )
    assert stolen.status_code == 404
    assert stolen.json()["code"] == 40420


def test_cannot_attach_foreign_tenant_role(client: TestClient) -> None:
    alice, alice_id = register_and_login(client, "rbac-fk-alice@example.com")
    bob, _b = register_and_login(client, "rbac-fk-bob@example.com")
    alice_tenant = _create_tenant(client, alice, "FkAlice", "rbac-fk-a")
    bob_tenant = _create_tenant(client, bob, "FkBob", "rbac-fk-b")
    bob_admin_id = _role_map(client, bob, bob_tenant)["ADMIN"]["id"]
    session = SessionLocal()
    try:
        member = session.scalars(
            select(TenantMember).where(
                TenantMember.tenant_id == alice_tenant,
                TenantMember.user_id == alice_id,
            )
        ).one()
        with pytest.raises(AppError) as exc:
            RoleService(session).assign_member_role(
                tenant_id=alice_tenant,
                member_id=member.id,
                role_id=bob_admin_id,
                commit=True,
            )
        assert exc.value.code == 40420
        session.rollback()
        session.add(
            MemberRoleGrant(
                tenant_id=alice_tenant,
                member_id=member.id,
                role_id=bob_admin_id,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    finally:
        session.close()


def test_role_code_unique_per_tenant_but_reusable_across_tenants(client: TestClient) -> None:
    alice, _a = register_and_login(client, "rbac-code-a@example.com")
    bob, _b = register_and_login(client, "rbac-code-b@example.com")
    alice_tenant = _create_tenant(client, alice, "CodeA", "rbac-code-a")
    bob_tenant = _create_tenant(client, bob, "CodeB", "rbac-code-b")
    first = client.post(
        "/api/v1/roles",
        json={"name": "值班", "code": "DUTY", "permission_ids": []},
        headers=auth_header(alice, alice_tenant),
    )
    assert first.status_code == 200, first.text
    duplicate = client.post(
        "/api/v1/roles",
        json={"name": "值班2", "code": "DUTY", "permission_ids": []},
        headers=auth_header(alice, alice_tenant),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == 40920
    other = client.post(
        "/api/v1/roles",
        json={"name": "值班", "code": "DUTY", "permission_ids": []},
        headers=auth_header(bob, bob_tenant),
    )
    assert other.status_code == 200, other.text


def test_unauthenticated_role_api_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/roles")
    assert response.status_code == 401
    assert response.json()["code"] == 40100


def test_missing_permission_returns_403(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "rbac-403-owner@example.com")
    member_token, member_id = register_and_login(client, "rbac-403-member@example.com")
    tenant_id = _create_tenant(client, owner, "Forbidden", "rbac-403")
    _add_member(client, owner, tenant_id, member_id)
    response = client.delete(
        f"/api/v1/roles/{_role_map(client, owner, tenant_id)['VIEWER']['id']}",
        headers=auth_header(member_token, tenant_id),
    )
    assert response.status_code == 403
    assert response.json()["code"] == 40320


def test_disabled_member_cannot_pass_permission_check(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "rbac-dis-owner@example.com")
    member_token, member_id = register_and_login(client, "rbac-dis-member@example.com")
    tenant_id = _create_tenant(client, owner, "DisMem", "rbac-dism")
    member_row_id = _add_member(client, owner, tenant_id, member_id)
    patched = client.patch(
        f"/api/v1/tenants/{tenant_id}/members/{member_row_id}",
        json={"status": MemberStatus.DISABLED.value},
        headers=auth_header(owner, tenant_id),
    )
    assert patched.status_code == 200
    response = client.get("/api/v1/roles", headers=auth_header(member_token, tenant_id))
    assert response.status_code == 403
    assert response.json()["code"] == 40310


def test_disabled_tenant_cannot_pass_permission_check(client: TestClient) -> None:
    token, _user_id = register_and_login(client, "rbac-dis-tenant@example.com")
    tenant_id = _create_tenant(client, token, "DisTen", "rbac-dist")
    session = SessionLocal()
    try:
        session.execute(
            text("UPDATE tenants SET status = :status WHERE id = :id"),
            {"status": TenantStatus.DISABLED.value, "id": tenant_id},
        )
        session.commit()
    finally:
        session.close()
    response = client.get("/api/v1/roles", headers=auth_header(token, tenant_id))
    assert response.status_code == 403
    assert response.json()["code"] == 40310


def test_replace_role_permissions_rolls_back_on_error(client: TestClient, monkeypatch) -> None:
    token, _user_id = register_and_login(client, "rbac-tx@example.com")
    tenant_id = _create_tenant(client, token, "TxCo", "rbac-tx")
    catalog = client.get("/api/v1/permissions", headers=auth_header(token, tenant_id))
    assert catalog.status_code == 200, catalog.text
    permission_ids = [item["id"] for item in catalog.json()["data"][:2]]
    created = client.post(
        "/api/v1/roles",
        json={"name": "事务", "code": "TXROLE", "permission_ids": permission_ids},
        headers=auth_header(token, tenant_id),
    )
    assert created.status_code == 200, created.text
    role_id = created.json()["data"]["id"]
    original = {item["id"] for item in created.json()["data"]["permissions"]}

    def explode(self, *, tenant_id: int, role_id: int, permission_ids: list[int]) -> None:
        self.session.execute(
            delete(RolePermission).where(
                RolePermission.tenant_id == tenant_id,
                RolePermission.role_id == role_id,
            )
        )
        self.session.flush()
        raise RuntimeError("mid replace")

    monkeypatch.setattr(RoleRepository, "replace_permissions", explode)
    session = SessionLocal()
    try:
        context = AuthorizationService(session).build_context(
            user_id=_user_id,
            tenant_id=tenant_id,
        )
        with pytest.raises(RuntimeError, match="mid replace"):
            RoleService(session).replace_role_permissions(context, role_id, [])
    finally:
        session.close()

    detail = client.get(f"/api/v1/roles/{role_id}", headers=auth_header(token, tenant_id))
    assert {item["id"] for item in detail.json()["data"]["permissions"]} == original


def test_system_roles_cannot_be_mutated_via_api(client: TestClient) -> None:
    token, _user_id = register_and_login(client, "rbac-sys@example.com")
    tenant_id = _create_tenant(client, token, "SysCo", "rbac-sys")
    owner_id = _role_map(client, token, tenant_id)["OWNER"]["id"]
    patched = client.patch(
        f"/api/v1/roles/{owner_id}",
        json={"name": "被改名"},
        headers=auth_header(token, tenant_id),
    )
    assert patched.status_code == 400
    assert patched.json()["code"] == 40040
    replaced = client.put(
        f"/api/v1/roles/{owner_id}/permissions",
        json={"permission_ids": []},
        headers=auth_header(token, tenant_id),
    )
    assert replaced.status_code == 400
    assert replaced.json()["code"] == 40040
    deleted = client.delete(f"/api/v1/roles/{owner_id}", headers=auth_header(token, tenant_id))
    assert deleted.status_code == 400
    assert deleted.json()["code"] == 40040
    admin_id = _role_map(client, token, tenant_id)["ADMIN"]["id"]
    admin_deleted = client.delete(
        f"/api/v1/roles/{admin_id}",
        headers=auth_header(token, tenant_id),
    )
    assert admin_deleted.status_code == 400
    assert admin_deleted.json()["code"] == 40040


def test_cannot_delete_in_use_role_or_last_owner(client: TestClient) -> None:
    owner, owner_user_id = register_and_login(client, "rbac-last-owner@example.com")
    tenant_id = _create_tenant(client, owner, "LastCo", "rbac-last")
    created = client.post(
        "/api/v1/roles",
        json={"name": "值班", "code": "DUTY", "permission_ids": []},
        headers=auth_header(owner, tenant_id),
    )
    assert created.status_code == 200, created.text
    duty_id = created.json()["data"]["id"]
    owner_role_id = _role_map(client, owner, tenant_id)["OWNER"]["id"]
    member_id = 0

    session = SessionLocal()
    try:
        member = session.scalars(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == owner_user_id,
            )
        ).one()
        member_id = member.id
        RoleService(session).assign_member_role(
            tenant_id=tenant_id,
            member_id=member_id,
            role_id=duty_id,
            commit=True,
        )
        in_use = client.delete(f"/api/v1/roles/{duty_id}", headers=auth_header(owner, tenant_id))
        assert in_use.status_code == 400
        assert in_use.json()["code"] == 40041
        assert "1 名成员" in in_use.json()["message"]
        with pytest.raises(AppError) as exc:
            RoleService(session).revoke_member_role(
                tenant_id=tenant_id,
                member_id=member_id,
                role_id=owner_role_id,
            )
        assert exc.value.code == 40034
        session.rollback()
        owner_context = AuthorizationService(session).build_context(
            user_id=owner_user_id,
            tenant_id=tenant_id,
        )
        with pytest.raises(AppError) as grant_exc:
            RoleService(session).assign_member_role(
                tenant_id=tenant_id,
                member_id=member_id,
                role_id=owner_role_id,
                actor=owner_context,
                commit=True,
            )
        assert grant_exc.value.code == 40321
    finally:
        session.close()

    disabled = client.patch(
        f"/api/v1/tenants/{tenant_id}/members/{member_id}",
        json={"status": MemberStatus.DISABLED.value},
        headers=auth_header(owner, tenant_id),
    )
    assert disabled.status_code == 400
    assert disabled.json()["code"] == 40034


def test_historical_owner_backfill_keeps_access(client: TestClient) -> None:
    owner, owner_user_id = register_and_login(client, "rbac-hist-owner@example.com")
    member_token, member_user_id = register_and_login(client, "rbac-hist-member@example.com")
    tenant_id = _create_tenant(client, owner, "HistCo", "rbac-hist")
    _add_member(client, owner, tenant_id, member_user_id)

    session = SessionLocal()
    try:
        session.execute(
            text("DELETE FROM role_permissions WHERE tenant_id = :id"),
            {"id": tenant_id},
        )
        session.execute(text("DELETE FROM member_roles WHERE tenant_id = :id"), {"id": tenant_id})
        session.execute(text("DELETE FROM roles WHERE tenant_id = :id"), {"id": tenant_id})
        session.commit()
        RoleService(session).backfill_existing_tenants()
        session.commit()
        owner_member = session.scalars(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == owner_user_id,
            )
        ).one()
        member = session.scalars(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == member_user_id,
            )
        ).one()
        assert owner_member.role == MemberRole.OWNER.value
        owner_grants = {
            row.role.code
            for row in RoleRepository(session).list_grants_for_member(
                tenant_id=tenant_id,
                member_id=owner_member.id,
            )
        }
        member_grants = {
            row.role.code
            for row in RoleRepository(session).list_grants_for_member(
                tenant_id=tenant_id,
                member_id=member.id,
            )
        }
        assert SystemRoleCode.OWNER in owner_grants
        assert SystemRoleCode.VIEWER in member_grants
        assert SystemRoleCode.OWNER not in member_grants
    finally:
        session.close()

    listed = client.get("/api/v1/roles", headers=auth_header(owner, tenant_id))
    assert listed.status_code == 200
    member_listed = client.get("/api/v1/roles", headers=auth_header(member_token, tenant_id))
    assert member_listed.status_code == 200


def test_unknown_permission_code_is_server_error(client: TestClient) -> None:
    token, user_id = register_and_login(client, "rbac-unknown@example.com")
    tenant_id = _create_tenant(client, token, "UnkCo", "rbac-unk")
    session = SessionLocal()
    try:
        context = AuthorizationService(session).build_context(user_id=user_id, tenant_id=tenant_id)
        with pytest.raises(AppError) as exc:
            AuthorizationService(session).require_all(context, ("not:a:real:code",))
        assert exc.value.code == 50021
        assert exc.value.status_code == 500
    finally:
        session.close()


def test_custom_role_crud_and_cannot_use_unknown_permission_id(client: TestClient) -> None:
    token, _user_id = register_and_login(client, "rbac-crud@example.com")
    tenant_id = _create_tenant(client, token, "CrudCo", "rbac-crud")
    catalog = client.get(
        "/api/v1/permissions",
        headers=auth_header(token, tenant_id),
    ).json()["data"]
    permission_id = catalog[0]["id"]
    created = client.post(
        "/api/v1/roles",
        json={
            "name": "客服",
            "code": "support",
            "description": "只看订单",
            "permission_ids": [permission_id],
        },
        headers=auth_header(token, tenant_id),
    )
    assert created.status_code == 200, created.text
    role_id = created.json()["data"]["id"]
    assert created.json()["data"]["code"] == "SUPPORT"
    patched = client.patch(
        f"/api/v1/roles/{role_id}",
        json={"name": "高级客服"},
        headers=auth_header(token, tenant_id),
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "高级客服"
    bad = client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"permission_ids": [permission_id, 999999]},
        headers=auth_header(token, tenant_id),
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == 40042
    deleted = client.delete(f"/api/v1/roles/{role_id}", headers=auth_header(token, tenant_id))
    assert deleted.status_code == 200


def test_create_tenant_rolls_back_when_role_bootstrap_fails(
    client: TestClient,
    monkeypatch,
) -> None:
    token, _user_id = register_and_login(client, "rbac-boot-fail@example.com")

    def boom(self, *, tenant_id: int, owner_member_id: int | None) -> None:  # noqa: ANN001
        raise RuntimeError("bootstrap fail")

    monkeypatch.setattr(RoleService, "bootstrap_tenant", boom)
    with pytest.raises(RuntimeError, match="bootstrap fail"):
        client.post(
            "/api/v1/tenants",
            json={"name": "Ghost", "code": "rbac-ghost"},
            headers=auth_header(token),
        )
    session = SessionLocal()
    try:
        tenants = session.execute(text("SELECT COUNT(*) FROM tenants")).scalar()
        roles = session.execute(text("SELECT COUNT(*) FROM roles")).scalar()
        assert tenants == 0
        assert roles == 0
    finally:
        session.close()


def test_admin_permissions_can_change_but_must_keep_tenant_management(client: TestClient) -> None:
    token, _user_id = register_and_login(client, "rbac-admin-perm@example.com")
    tenant_id = _create_tenant(client, token, "AdmPerm", "rbac-admperm")
    roles = _role_map(client, token, tenant_id)
    catalog = client.get(
        "/api/v1/permissions",
        headers=auth_header(token, tenant_id),
    ).json()["data"]
    by_code = {item["code"]: item["id"] for item in catalog}
    keep = [by_code[code] for code in ADMIN_REQUIRED_PERMISSION_CODES]
    keep.append(by_code[PermissionCode.PRODUCT_READ])
    updated = client.put(
        f"/api/v1/roles/{roles['ADMIN']['id']}/permissions",
        json={"permission_ids": keep},
        headers=auth_header(token, tenant_id),
    )
    assert updated.status_code == 200, updated.text
    codes = {item["code"] for item in updated.json()["data"]["permissions"]}
    assert PermissionCode.PRODUCT_READ in codes
    assert PermissionCode.TENANT_ROLE_DELETE in codes
    stripped = client.put(
        f"/api/v1/roles/{roles['ADMIN']['id']}/permissions",
        json={"permission_ids": [by_code[PermissionCode.PRODUCT_READ]]},
        headers=auth_header(token, tenant_id),
    )
    assert stripped.status_code == 400
    assert stripped.json()["code"] == 40040
    operator = client.put(
        f"/api/v1/roles/{roles['OPERATOR']['id']}/permissions",
        json={"permission_ids": [by_code[PermissionCode.INVENTORY_READ]]},
        headers=auth_header(token, tenant_id),
    )
    assert operator.status_code == 200, operator.text
    assert {item["code"] for item in operator.json()["data"]["permissions"]} == {
        PermissionCode.INVENTORY_READ
    }


def test_permission_change_takes_effect_on_next_request(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "rbac-live-owner@example.com")
    member_token, _mid = register_and_login(client, "rbac-live-admin@example.com")
    tenant_id = _create_tenant(client, owner, "LiveCo", "rbac-live")
    roles = _role_map(client, owner, tenant_id)
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": "rbac-live-admin@example.com", "role_ids": [roles["ADMIN"]["id"]]},
        headers=auth_header(owner, tenant_id),
    )
    assert added.status_code == 200, added.text
    before = client.get(
        "/api/v1/tenants/current/my-permissions",
        headers=auth_header(member_token, tenant_id),
    )
    assert PermissionCode.TENANT_ROLE_MANAGE in before.json()["data"]["permissions"]
    catalog = client.get(
        "/api/v1/permissions",
        headers=auth_header(owner, tenant_id),
    ).json()["data"]
    by_code = {item["code"]: item["id"] for item in catalog}
    keep = [
        by_code[code]
        for code in ADMIN_REQUIRED_PERMISSION_CODES
        if code != PermissionCode.TENANT_ROLE_DELETE
    ]
    keep.append(by_code[PermissionCode.TENANT_ROLE_READ])
    denied = client.put(
        f"/api/v1/roles/{roles['ADMIN']['id']}/permissions",
        json={"permission_ids": keep},
        headers=auth_header(owner, tenant_id),
    )
    assert denied.status_code == 400
    keep_all = [by_code[code] for code in ADMIN_REQUIRED_PERMISSION_CODES]
    updated = client.put(
        f"/api/v1/roles/{roles['ADMIN']['id']}/permissions",
        json={"permission_ids": keep_all},
        headers=auth_header(owner, tenant_id),
    )
    assert updated.status_code == 200, updated.text
    after = client.get(
        "/api/v1/tenants/current/my-permissions",
        headers=auth_header(member_token, tenant_id),
    )
    assert PermissionCode.PRODUCT_CREATE not in after.json()["data"]["permissions"]
    assert PermissionCode.TENANT_ROLE_CREATE in after.json()["data"]["permissions"]
    create_role = client.post(
        "/api/v1/roles",
        json={"name": "临时", "code": "TEMPLIVE", "permission_ids": []},
        headers=auth_header(member_token, tenant_id),
    )
    assert create_role.status_code == 200
