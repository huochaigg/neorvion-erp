import pytest
from app.db.session import SessionLocal
from app.models.tenant import MemberStatus, TenantStatus
from app.repositories.tenant import TenantMemberRepository
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers.auth_api import auth_header, register_and_login


def _create_tenant(client: TestClient, token: str, name: str = "Acme", code: str | None = None):
    payload: dict[str, str] = {"name": name}
    if code:
        payload["code"] = code
    response = client.post("/api/v1/tenants", json=payload, headers=auth_header(token))
    return response


def test_cannot_create_tenant_when_anonymous(client: TestClient) -> None:
    response = client.post("/api/v1/tenants", json={"name": "Acme"})
    assert response.status_code == 401
    assert response.json()["code"] == 40100


def test_login_user_can_create_tenant_and_owner_membership(client: TestClient) -> None:
    token, user_id = register_and_login(client, "owner@example.com", "Owner")
    response = _create_tenant(client, token, "Acme", "acme-one")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["name"] == "Acme"
    assert data["code"] == "acme-one"
    assert data["is_owner"] is True
    assert data["my_role"] == "OWNER"
    members = client.get(f"/api/v1/tenants/{data['id']}/members", headers=auth_header(token))
    assert members.status_code == 200
    rows = members.json()["data"]
    assert len(rows) == 1
    assert rows[0]["user_id"] == user_id
    assert rows[0]["role"] == "OWNER"


def test_create_tenant_rolls_back_when_member_fails(
    client: TestClient,
    monkeypatch,
) -> None:
    token, _user_id = register_and_login(client, "rollback@example.com")

    def boom(self, member):  # noqa: ANN001
        raise RuntimeError("member fail")

    monkeypatch.setattr(TenantMemberRepository, "add", boom)
    with pytest.raises(RuntimeError, match="member fail"):
        _create_tenant(client, token, "Ghost")
    session = SessionLocal()
    try:
        tenants = session.execute(text("SELECT COUNT(*) FROM tenants")).scalar()
        members = session.execute(text("SELECT COUNT(*) FROM tenant_members")).scalar()
        assert tenants == 0
        assert members == 0
    finally:
        session.close()


def test_user_can_belong_to_multiple_tenants(client: TestClient) -> None:
    token, _user_id = register_and_login(client, "multi@example.com")
    first = _create_tenant(client, token, "One", "tenant-one")
    second = _create_tenant(client, token, "Two", "tenant-two")
    assert first.status_code == 200
    assert second.status_code == 200
    listed = client.get("/api/v1/tenants", headers=auth_header(token))
    assert listed.status_code == 200
    codes = {item["code"] for item in listed.json()["data"]}
    assert codes == {"tenant-one", "tenant-two"}


def test_cannot_join_same_tenant_twice(client: TestClient) -> None:
    owner_token, _owner_id = register_and_login(client, "dup-owner@example.com", "DupOwner")
    member_token, member_id = register_and_login(client, "dup-member@example.com", "DupMember")
    tenant_id = _create_tenant(client, owner_token, "DupCo", "dup-co").json()["data"]["id"]
    first = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"user_id": member_id},
        headers=auth_header(owner_token),
    )
    assert first.status_code == 200, first.text
    second = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"user_id": member_id},
        headers=auth_header(owner_token),
    )
    assert second.status_code == 409
    assert second.json()["code"] == 40911
    listed = client.get("/api/v1/tenants", headers=auth_header(member_token))
    assert len(listed.json()["data"]) == 1


def test_tenant_list_only_returns_joined_tenants(client: TestClient) -> None:
    alice, _a = register_and_login(client, "alice-t@example.com", "Alice")
    bob, _b = register_and_login(client, "bob-t@example.com", "Bob")
    alice_tenant = _create_tenant(client, alice, "AliceCo", "alice-co").json()["data"]["id"]
    _create_tenant(client, bob, "BobCo", "bob-co")
    listed = client.get("/api/v1/tenants", headers=auth_header(alice))
    ids = {item["id"] for item in listed.json()["data"]}
    assert ids == {alice_tenant}


def test_cannot_read_foreign_tenant_or_members(client: TestClient) -> None:
    alice, _a = register_and_login(client, "alice-x@example.com")
    bob, _b = register_and_login(client, "bob-x@example.com")
    bob_tenant = _create_tenant(client, bob, "Secret", "secret-co").json()["data"]["id"]
    detail = client.get(f"/api/v1/tenants/{bob_tenant}", headers=auth_header(alice))
    assert detail.status_code == 404
    assert detail.json()["code"] == 40410
    members = client.get(f"/api/v1/tenants/{bob_tenant}/members", headers=auth_header(alice))
    assert members.status_code == 404
    assert members.json()["message"] == "租户不存在或不可访问"


def test_invalid_tenant_header_cannot_bypass_membership(client: TestClient) -> None:
    token, _user_id = register_and_login(client, "header@example.com")
    tenant_id = _create_tenant(client, token, "HeaderCo", "header-co").json()["data"]["id"]
    missing = client.get("/api/v1/tenants/current", headers=auth_header(token))
    assert missing.status_code == 400
    assert missing.json()["code"] == 40030
    unknown = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id=999999))
    assert unknown.status_code == 404
    assert unknown.json()["code"] == 40410
    ok = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id))
    assert ok.status_code == 200
    assert ok.json()["data"]["tenant_id"] == tenant_id
    assert ok.json()["data"]["is_owner"] is True


def test_disabled_member_cannot_enter_tenant(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "dis-owner@example.com")
    member_token, member_id = register_and_login(client, "dis-member@example.com")
    tenant_id = _create_tenant(client, owner, "DisableCo", "disable-co").json()["data"]["id"]
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"user_id": member_id},
        headers=auth_header(owner),
    )
    member_row_id = added.json()["data"]["id"]
    patched = client.patch(
        f"/api/v1/tenants/{tenant_id}/members/{member_row_id}",
        json={"status": MemberStatus.DISABLED.value},
        headers=auth_header(owner),
    )
    assert patched.status_code == 200
    context = client.get("/api/v1/tenants/current", headers=auth_header(member_token, tenant_id))
    assert context.status_code == 403
    assert context.json()["code"] == 40310
    members = client.get(f"/api/v1/tenants/{tenant_id}/members", headers=auth_header(member_token))
    assert members.status_code == 403


def test_disabled_tenant_cannot_be_used(client: TestClient) -> None:
    token, _user_id = register_and_login(client, "tenant-off@example.com")
    tenant_id = _create_tenant(client, token, "OffCo", "off-co").json()["data"]["id"]
    session = SessionLocal()
    try:
        session.execute(
            text("UPDATE tenants SET status = :status WHERE id = :id"),
            {"status": TenantStatus.DISABLED.value, "id": tenant_id},
        )
        session.commit()
    finally:
        session.close()
    context = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id))
    assert context.status_code == 403
    assert context.json()["code"] == 40310


def test_owner_can_manage_members_regular_member_cannot(client: TestClient) -> None:
    owner, _oid = register_and_login(client, "mgr-owner@example.com")
    member_token, member_id = register_and_login(client, "mgr-member@example.com")
    outsider_token, outsider_id = register_and_login(client, "mgr-out@example.com")
    tenant_id = _create_tenant(client, owner, "MgrCo", "mgr-co").json()["data"]["id"]
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"user_id": member_id},
        headers=auth_header(owner),
    )
    assert added.status_code == 200
    forbidden = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"user_id": outsider_id},
        headers=auth_header(member_token),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == 40311
    other_tenant = _create_tenant(client, outsider_token, "Other", "other-co").json()["data"]["id"]
    cross = client.post(
        f"/api/v1/tenants/{other_tenant}/members",
        json={"user_id": member_id},
        headers=auth_header(owner),
    )
    assert cross.status_code == 404


def test_redis_tenant_keys_include_tenant_id() -> None:
    from app.core.redis_keys import tenant_cache_key

    assert tenant_cache_key(1001, "product", 1) == "erp:tenant:1001:product:1"
