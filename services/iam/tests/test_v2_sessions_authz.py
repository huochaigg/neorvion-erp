from tests.helpers.auth_api import auth_header, register_and_login


def test_list_and_revoke_session(client) -> None:
    token, _user_id = register_and_login(client, "session-user@example.com")
    listed = client.get("/api/v1/sessions", headers=auth_header(token))
    assert listed.status_code == 200, listed.text
    items = listed.json()["data"]
    assert len(items) >= 1
    current = next(item for item in items if item["current"])
    assert current["revoked_at"] is None

    revoked = client.delete(f"/api/v1/sessions/{current['id']}", headers=auth_header(token))
    assert revoked.status_code == 200, revoked.text
    me = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert me.status_code == 401


def test_refresh_replay_revokes_family(client) -> None:
    token, _user_id = register_and_login(client, "replay@example.com")
    old_refresh = client.cookies.get("neorvion_refresh")
    old_csrf = client.cookies.get("neorvion_csrf")
    assert old_refresh and old_csrf

    first = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": old_csrf})
    assert first.status_code == 200, first.text
    new_token = first.json()["data"]["access_token"]
    assert new_token

    client.cookies.set("neorvion_refresh", old_refresh)
    client.cookies.set("neorvion_csrf", old_csrf)
    replay = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": old_csrf})
    assert replay.status_code == 401

    me = client.get("/api/v1/auth/me", headers=auth_header(new_token))
    assert me.status_code == 401


def test_authorize_uses_database_not_stale_snapshot(client) -> None:
    token, _user_id = register_and_login(client, "authz-owner@example.com", "Owner")
    created = client.post(
        "/api/v1/tenants",
        headers=auth_header(token),
        json={"name": "AuthzCo", "code": "authzco"},
    )
    assert created.status_code == 200, created.text
    tenant_id = created.json()["data"]["id"]

    from app.core.redis import redis_client
    from neorvion_security.snapshot import snapshot_key

    redis_client.delete(snapshot_key(_user_id, tenant_id))

    denied = client.post(
        "/api/v1/internal/authorize",
        headers={
            **auth_header(token, tenant_id),
            "X-Internal-Key": "wrong-key",
        },
        json={"codes": ["order:read"], "high_risk": True},
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/api/v1/internal/authorize",
        headers={
            **auth_header(token, tenant_id),
            "X-Internal-Key": "iam-test-internal-key",
        },
        json={"codes": ["order:read"], "high_risk": True},
    )
    assert allowed.status_code == 200, allowed.text
    data = allowed.json()["data"]
    assert data["high_risk_verified"] is True
    assert data["authz_source"] == "iam-db"
    assert "order:read" in data["permission_codes"]
    assert "knowledge:create" in data["permission_codes"]


def test_authorize_rejects_missing_permission(client) -> None:
    token, _user_id = register_and_login(client, "authz-owner2@example.com")
    created = client.post(
        "/api/v1/tenants",
        headers=auth_header(token),
        json={"name": "AuthzCo2", "code": "authzco2"},
    )
    tenant_id = created.json()["data"]["id"]
    register_and_login(client, "authz-viewer@example.com", "Viewer")
    invited = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=auth_header(token, tenant_id),
        json={"email": "authz-viewer@example.com"},
    )
    assert invited.status_code == 200, invited.text

    from tests.helpers.auth_api import encrypted_fields

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "authz-viewer@example.com", **encrypted_fields(client)},
    )
    viewer_token = login.json()["data"]["access_token"]
    forbidden = client.post(
        "/api/v1/internal/authorize",
        headers={
            **auth_header(viewer_token, tenant_id),
            "X-Internal-Key": "iam-test-internal-key",
        },
        json={"codes": ["refund:confirm"], "high_risk": True},
    )
    assert forbidden.status_code == 403
