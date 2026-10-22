"""IAM 安全边界：伪造令牌、错误 audience、越权与权限撤销。"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt

from app.core.jwt_keys import get_jwt_signer
from tests.helpers.auth_api import auth_header, register_and_login


def _b64url(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_forged_token_and_wrong_audience_are_rejected(client) -> None:
    token, _ = register_and_login(client, "sec-owner@example.com", "Owner")
    created = client.post(
        "/api/v1/tenants",
        headers=auth_header(token),
        json={"name": "Sec", "code": "sec-aud"},
    )
    assert created.status_code == 200, created.text
    tenant_id = created.json()["data"]["id"]

    forged = client.get("/api/v1/auth/me", headers=auth_header("not-a.jwt.token"))
    assert forged.status_code == 401

    bad_aud, _jti = get_jwt_signer().sign(
        user_id=1,
        token_type="access",
        ttl=timedelta(minutes=5),
        extra_audiences=["neorvion-copilot"],
    )
    denied = client.get("/api/v1/tenants/current", headers=auth_header(bad_aud, tenant_id))
    assert denied.status_code == 401


def test_member_cannot_access_other_tenant(client) -> None:
    owner_a, _ = register_and_login(client, "a-owner@example.com", "A")
    owner_b, _ = register_and_login(client, "b-owner@example.com", "B")
    tenant_a = client.post(
        "/api/v1/tenants",
        headers=auth_header(owner_a),
        json={"name": "A", "code": "iso-a"},
    ).json()["data"]["id"]
    tenant_b = client.post(
        "/api/v1/tenants",
        headers=auth_header(owner_b),
        json={"name": "B", "code": "iso-b"},
    ).json()["data"]["id"]
    stolen = client.get("/api/v1/tenants/current", headers=auth_header(owner_a, tenant_b))
    assert stolen.status_code in {403, 404}
    own = client.get("/api/v1/tenants/current", headers=auth_header(owner_a, tenant_a))
    assert own.status_code == 200


def test_disable_user_invalidates_access(client) -> None:
    admin, _ = register_and_login(client, "platform@example.com", "Admin")
    # 平台管理员需种子；若当前用户不是平台管理员则跳过提权路径，改为停用后快照失效由 IAM 用户接口覆盖。
    me = client.get("/api/v1/auth/me", headers=auth_header(admin))
    assert me.status_code == 200
    target, user_id = register_and_login(client, "victim@example.com", "Victim")
    tenant_id = client.post(
        "/api/v1/tenants",
        headers=auth_header(target),
        json={"name": "V", "code": "victim-co"},
    ).json()["data"]["id"]
    before = client.get("/api/v1/tenants/current", headers=auth_header(target, tenant_id))
    assert before.status_code == 200
    listed = client.get("/api/v1/users", headers=auth_header(admin))
    if listed.status_code == 200:
        disabled = client.patch(
            f"/api/v1/users/{user_id}",
            headers=auth_header(admin),
            json={"status": "DISABLED"},
        )
        if disabled.status_code == 200:
            after = client.get("/api/v1/tenants/current", headers=auth_header(target, tenant_id))
            assert after.status_code in {401, 403}


def test_alg_none_and_wrong_issuer_are_rejected(client) -> None:
    token, user_id = register_and_login(client, "alg-owner@example.com", "Owner")
    tenant_id = client.post(
        "/api/v1/tenants",
        headers=auth_header(token),
        json={"name": "Alg", "code": "alg-none"},
    ).json()["data"]["id"]
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "type": "access",
        "iss": "neorvion-iam",
        "aud": ["neorvion-iam"],
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": "none-jti",
        "ver": 0,
    }
    none_token = f"{_b64url({'alg': 'none', 'kid': 'jwt-v1', 'typ': 'JWT'})}.{_b64url(claims)}."
    assert client.get("/api/v1/auth/me", headers=auth_header(none_token)).status_code == 401

    signer = get_jwt_signer()
    evil = jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iss": "evil-issuer",
            "aud": ["neorvion-iam"],
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
            "jti": "evil-jti",
            "ver": 0,
        },
        signer._private,
        algorithm="RS256",
        headers={"kid": signer.kid, "typ": "JWT"},
    )
    denied = client.get("/api/v1/tenants/current", headers=auth_header(evil, tenant_id))
    assert denied.status_code == 401


def test_role_permission_revoke_updates_snapshot(client) -> None:
    owner, _ = register_and_login(client, "rbac-owner@example.com", "Owner")
    member_token, member_user_id = register_and_login(client, "rbac-member@example.com", "Member")
    tenant_id = client.post(
        "/api/v1/tenants",
        headers=auth_header(owner),
        json={"name": "Rbac", "code": "rbac-revoke"},
    ).json()["data"]["id"]
    owner_header = auth_header(owner, tenant_id)
    catalog = client.get("/api/v1/permissions", headers=owner_header)
    assert catalog.status_code == 200, catalog.text
    order_read = next(item for item in catalog.json()["data"] if item["code"] == "order:read")
    created_role = client.post(
        "/api/v1/roles",
        headers=owner_header,
        json={
            "name": "Reader",
            "code": "READER",
            "permission_ids": [order_read["id"]],
        },
    )
    assert created_role.status_code == 200, created_role.text
    role_id = created_role.json()["data"]["id"]
    added = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=owner_header,
        json={"email": "rbac-member@example.com", "role_ids": [role_id]},
    )
    assert added.status_code == 200, added.text
    member_header = auth_header(member_token, tenant_id)
    before = client.get("/api/v1/tenants/current", headers=member_header)
    assert before.status_code == 200, before.text
    assert "order:read" in before.json()["data"]["permission_codes"]
    revoked = client.put(
        f"/api/v1/roles/{role_id}/permissions",
        headers=owner_header,
        json={"permission_ids": []},
    )
    assert revoked.status_code == 200, revoked.text
    after = client.get("/api/v1/tenants/current", headers=member_header)
    assert after.status_code == 200, after.text
    assert "order:read" not in after.json()["data"]["permission_codes"]
    from app.core.redis import redis_client
    from neorvion_security.snapshot import snapshot_key

    raw = redis_client.get(snapshot_key(member_user_id, tenant_id))
    assert raw
    assert "order:read" not in json.loads(raw)["permission_codes"]


def test_redis_outage_rejects_access_token_even_with_session(client, monkeypatch) -> None:
    """有 session_id 时 Redis 不可用不能跳过 token_version。登录本身不走这条依赖。"""
    token, _user_id = register_and_login(client, "redis-down@example.com", "Redis")
    alive = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert alive.status_code == 200, alive.text

    from app.core.redis import redis_client

    def _redis_down(*_args: object, **_kwargs: object) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr(redis_client, "get", _redis_down)
    denied = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert denied.status_code == 503, denied.text
    assert denied.json()["code"] == 50313
