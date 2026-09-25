from datetime import timedelta

from app.core.config import settings
from app.core.security import create_token, digest_password
from app.db.session import SessionLocal
from app.models.user import UserStatus
from fastapi.testclient import TestClient
from sqlalchemy import text

PLAIN_PASSWORD = "Passw0rd!"
REGISTER_PAYLOAD = {
    "email": "alice@example.com",
    "password": digest_password(PLAIN_PASSWORD),
    "display_name": "Alice",
}


def _register(client: TestClient, **overrides: str) -> None:
    payload = {**REGISTER_PAYLOAD, **overrides}
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 200, response.text


def _login(client: TestClient, **overrides: str):
    payload = {
        "email": REGISTER_PAYLOAD["email"],
        "password": REGISTER_PAYLOAD["password"],
        **overrides,
    }
    return client.post("/api/v1/auth/login", json=payload)


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_register_success(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["email"] == "alice@example.com"
    assert "password_hash" not in body["data"]


def test_register_rejects_plaintext_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={**REGISTER_PAYLOAD, "password": PLAIN_PASSWORD},
    )
    assert response.status_code == 422


def test_register_stores_argon2id_not_plaintext(client: TestClient) -> None:
    _register(client)
    session = SessionLocal()
    try:
        stored = session.execute(
            text("SELECT password_hash FROM users WHERE email = :email"),
            {"email": REGISTER_PAYLOAD["email"]},
        ).scalar_one()
    finally:
        session.close()
    assert stored.startswith("$argon2id$")
    assert PLAIN_PASSWORD not in stored
    assert REGISTER_PAYLOAD["password"] not in stored


def test_register_duplicate_email(client: TestClient) -> None:
    _register(client)
    response = client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 409
    assert response.json()["code"] == 40011


def test_login_success(client: TestClient) -> None:
    _register(client)
    response = _login(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert settings.refresh_cookie_name in response.cookies


def test_login_wrong_password(client: TestClient) -> None:
    _register(client)
    response = _login(client, password=digest_password("wrong-pass"))
    assert response.status_code == 401
    assert response.json()["message"] == "邮箱或密码错误"


def test_access_token_can_read_me(client: TestClient) -> None:
    _register(client)
    access_token = _login(client).json()["data"]["access_token"]
    response = client.get("/api/v1/auth/me", headers=_auth_header(access_token))
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "alice@example.com"


def test_expired_access_token_rejected(client: TestClient) -> None:
    _register(client)
    access_token = _login(client).json()["data"]["access_token"]
    me = client.get("/api/v1/auth/me", headers=_auth_header(access_token)).json()["data"]
    expired, _jti = create_token(
        user_id=me["id"],
        token_type="access",
        expires_delta=timedelta(seconds=-30),
    )
    response = client.get("/api/v1/auth/me", headers=_auth_header(expired))
    assert response.status_code == 401
    assert response.json()["code"] == 40103


def test_refresh_issues_new_access_token(client: TestClient) -> None:
    _register(client)
    login_response = _login(client)
    old_access = login_response.json()["data"]["access_token"]
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    new_access = response.json()["data"]["access_token"]
    assert new_access
    assert new_access != old_access
    me = client.get("/api/v1/auth/me", headers=_auth_header(new_access))
    assert me.status_code == 200


def test_refresh_token_cannot_access_me(client: TestClient) -> None:
    _register(client)
    _login(client)
    refresh_token = client.cookies.get(settings.refresh_cookie_name)
    assert refresh_token
    response = client.get("/api/v1/auth/me", headers=_auth_header(refresh_token))
    assert response.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    _register(client)
    _login(client)
    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    refresh = client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 401


def test_me_requires_login(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == 40100


def test_disabled_user_cannot_access_me(client: TestClient) -> None:
    _register(client)
    access_token = _login(client).json()["data"]["access_token"]
    session = SessionLocal()
    try:
        session.execute(
            text("UPDATE users SET status = :status WHERE email = :email"),
            {"status": UserStatus.DISABLED.value, "email": REGISTER_PAYLOAD["email"]},
        )
        session.commit()
    finally:
        session.close()
    response = client.get("/api/v1/auth/me", headers=_auth_header(access_token))
    assert response.status_code == 403
    assert response.json()["code"] == 40300
