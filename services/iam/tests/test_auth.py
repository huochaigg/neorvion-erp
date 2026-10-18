from tests.helpers.auth_api import PLAIN_PASSWORD, auth_header, encrypted_fields, register_and_login


def test_register_login_me_and_refresh(client) -> None:
    token, user_id = register_and_login(client, "iam-user@example.com", "IAM")
    me = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert me.status_code == 200, me.text
    assert me.json()["data"]["id"] == user_id
    assert me.json()["data"]["is_platform_admin"] is False

    jwks = client.get("/.well-known/jwks.json")
    assert jwks.status_code == 200, jwks.text
    assert jwks.json()["keys"][0]["kid"] == "jwt-v1"
    assert jwks.json()["keys"][0]["alg"] == "RS256"

    csrf = client.cookies.get("neorvion_csrf")
    assert csrf
    refresh = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert refresh.status_code == 200, refresh.text
    new_token = refresh.json()["data"]["access_token"]
    assert new_token
    me2 = client.get("/api/v1/auth/me", headers=auth_header(new_token))
    assert me2.status_code == 200


def test_refresh_rejects_wrong_csrf(client) -> None:
    register_and_login(client, "csrf@example.com")
    refresh = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "not-the-token"})
    assert refresh.status_code == 401


def test_login_rejects_bad_password(client) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "bad@example.com", "display_name": "Bad", **encrypted_fields(client)},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "bad@example.com", **encrypted_fields(client, "WrongPass1")},
    )
    assert login.status_code == 401
    assert PLAIN_PASSWORD not in login.text


def test_create_tenant_and_snapshot_permissions(client) -> None:
    token, _user_id = register_and_login(client, "owner@example.com", "Owner")
    created = client.post(
        "/api/v1/tenants",
        headers=auth_header(token),
        json={"name": "Acme", "code": "acme"},
    )
    assert created.status_code == 200, created.text
    tenant_id = created.json()["data"]["id"]
    current = client.get("/api/v1/tenants/current", headers=auth_header(token, tenant_id))
    assert current.status_code == 200, current.text
    codes = current.json()["data"]["permission_codes"]
    assert "order:read" in codes
    assert "knowledge:read" in codes
    assert "iam:users:read" in codes
