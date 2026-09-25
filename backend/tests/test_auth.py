from datetime import timedelta
from time import sleep

from app.core import challenge_store, token_store
from app.core.config import settings
from app.core.redis import redis_client
from app.core.rsa_crypto import RSA_ALGORITHM, encrypt_with_public_pem, get_rsa_store
from app.core.security import create_token
from app.db.session import SessionLocal
from app.models.user import UserStatus
from fastapi.testclient import TestClient
from sqlalchemy import text

PLAIN_PASSWORD = "Passw0rd!"
REGISTER_EMAIL = "alice@example.com"
DISPLAY_NAME = "Alice"


def _public_key(client: TestClient) -> dict[str, object]:
    response = client.get("/api/crypto/public-key")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["algorithm"] == RSA_ALGORITHM
    assert "BEGIN PUBLIC KEY" in data["public_key"]
    assert "BEGIN PRIVATE KEY" not in data["public_key"]
    return data


def _encrypted_fields(client: TestClient, password: str = PLAIN_PASSWORD) -> dict[str, str]:
    material = _public_key(client)
    return {
        "encrypted_password": encrypt_with_public_pem(str(material["public_key"]), password),
        "key_id": str(material["key_id"]),
        "challenge_id": str(material["challenge_id"]),
    }


def _register_payload(client: TestClient, **overrides: str) -> dict[str, str]:
    payload = {
        "email": REGISTER_EMAIL,
        "display_name": DISPLAY_NAME,
        **_encrypted_fields(client),
        **overrides,
    }
    return payload


def _register(client: TestClient, **overrides: str) -> None:
    response = client.post("/api/v1/auth/register", json=_register_payload(client, **overrides))
    assert response.status_code == 200, response.text


def _login(client: TestClient, **overrides: str):
    payload = {
        "email": REGISTER_EMAIL,
        **_encrypted_fields(client),
        **overrides,
    }
    return client.post("/api/v1/auth/login", json=payload)


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_public_key_endpoint(client: TestClient) -> None:
    data = _public_key(client)
    assert data["key_id"] == settings.rsa_key_id
    assert data["expires_in"] == settings.rsa_challenge_ttl_seconds
    assert data["challenge_id"]
    assert redis_client.get(f"auth:challenge:{data['challenge_id']}") == data["key_id"]


def test_public_key_ignores_access_token(client: TestClient) -> None:
    response = client.get(
        "/api/crypto/public-key",
        headers=_auth_header("not-a-jwt"),
    )
    assert response.status_code == 200
    assert "BEGIN PRIVATE KEY" not in response.json()["data"]["public_key"]


def test_public_key_by_key_id(client: TestClient) -> None:
    previous_id = settings.rsa_previous_key_id
    response = client.get("/api/crypto/public-key", params={"key_id": previous_id})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["key_id"] == previous_id
    stored = redis_client.get(f"auth:challenge:{data['challenge_id']}")
    assert stored == previous_id


def test_public_key_unknown_key_id(client: TestClient) -> None:
    response = client.get("/api/crypto/public-key", params={"key_id": "retired"})
    assert response.status_code == 404
    assert response.json()["code"] == 40024


def test_register_success(client: TestClient) -> None:
    payload = _register_payload(client)
    assert "password" not in payload
    assert payload["encrypted_password"] != PLAIN_PASSWORD
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["email"] == REGISTER_EMAIL
    assert "password_hash" not in body["data"]


def test_register_rejects_plaintext_password(client: TestClient) -> None:
    payload = _register_payload(client)
    payload["password"] = PLAIN_PASSWORD
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_login_rejects_plaintext_password_field(client: TestClient) -> None:
    _register(client)
    payload = {
        "email": REGISTER_EMAIL,
        "password": PLAIN_PASSWORD,
        **_encrypted_fields(client),
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 422
    assert PLAIN_PASSWORD not in response.text


def test_login_request_does_not_contain_plaintext(client: TestClient) -> None:
    _register(client)
    payload = {"email": REGISTER_EMAIL, **_encrypted_fields(client)}
    assert "password" not in payload
    assert PLAIN_PASSWORD not in payload["encrypted_password"]
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200


def test_register_stores_argon2id_not_plaintext(client: TestClient) -> None:
    _register(client)
    session = SessionLocal()
    try:
        stored = session.execute(
            text("SELECT password_hash FROM users WHERE email = :email"),
            {"email": REGISTER_EMAIL},
        ).scalar_one()
    finally:
        session.close()
    assert stored.startswith("$argon2id$")
    assert PLAIN_PASSWORD not in stored


def test_register_duplicate_email(client: TestClient) -> None:
    first = _register_payload(client)
    assert client.post("/api/v1/auth/register", json=first).status_code == 200
    second = _register_payload(client)
    response = client.post("/api/v1/auth/register", json=second)
    assert response.status_code == 409
    assert response.json()["code"] == 40011


def test_login_success_after_rsa_encrypt(client: TestClient) -> None:
    _register(client)
    response = _login(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert settings.refresh_cookie_name in response.cookies


def test_login_wrong_password(client: TestClient) -> None:
    _register(client)
    response = _login(client, **_encrypted_fields(client, "Wrong0pass!"))
    assert response.status_code == 401
    assert response.json()["message"] == "邮箱或密码错误"


def test_expired_challenge_rejected(client: TestClient) -> None:
    material = _public_key(client)
    redis_client.pexpire(f"auth:challenge:{material['challenge_id']}", 1)
    sleep(0.05)
    payload = {
        "email": REGISTER_EMAIL,
        "display_name": DISPLAY_NAME,
        "encrypted_password": encrypt_with_public_pem(str(material["public_key"]), PLAIN_PASSWORD),
        "key_id": str(material["key_id"]),
        "challenge_id": str(material["challenge_id"]),
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == 40020


def test_challenge_cannot_be_reused(client: TestClient) -> None:
    payload = _register_payload(client)
    first = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 200
    reused = {
        **payload,
        "email": "bob@example.com",
        "display_name": "Bob",
    }
    response = client.post("/api/v1/auth/register", json=reused)
    assert response.status_code == 400
    assert response.json()["code"] == 40020


def test_invalid_ciphertext_rejected(client: TestClient) -> None:
    payload = _register_payload(client)
    payload["encrypted_password"] = "A" * 64
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == 40022
    assert "padding" not in response.json()["message"].lower()


def test_previous_key_id_accepted_during_rotation(client: TestClient) -> None:
    store = get_rsa_store()
    previous_id = settings.rsa_previous_key_id
    challenge_id = challenge_store.issue_challenge(previous_id)
    payload = {
        "email": "rotate@example.com",
        "display_name": "Rotate",
        "encrypted_password": encrypt_with_public_pem(
            store.public_pem_for(previous_id),
            PLAIN_PASSWORD,
        ),
        "key_id": previous_id,
        "challenge_id": challenge_id,
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 200, response.text


def test_unknown_key_id_rejected(client: TestClient) -> None:
    payload = _register_payload(client)
    payload["key_id"] = "unknown"
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["code"] == 40021


def test_access_token_can_read_me(client: TestClient) -> None:
    _register(client)
    access_token = _login(client).json()["data"]["access_token"]
    response = client.get("/api/v1/auth/me", headers=_auth_header(access_token))
    assert response.status_code == 200
    assert response.json()["data"]["email"] == REGISTER_EMAIL


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
            {"status": UserStatus.DISABLED.value, "email": REGISTER_EMAIL},
        )
        session.commit()
    finally:
        session.close()
    response = client.get("/api/v1/auth/me", headers=_auth_header(access_token))
    assert response.status_code == 403
    assert response.json()["code"] == 40300


def test_refresh_does_not_require_access_token(client: TestClient) -> None:
    _register(client)
    _login(client)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert "Authorization" not in response.request.headers
    assert response.json()["data"]["access_token"]


def test_refresh_ignores_expired_access_token_header(client: TestClient) -> None:
    _register(client)
    access_token = _login(client).json()["data"]["access_token"]
    me = client.get("/api/v1/auth/me", headers=_auth_header(access_token)).json()["data"]
    expired, _jti = create_token(
        user_id=me["id"],
        token_type="access",
        expires_delta=timedelta(seconds=-30),
    )
    response = client.post("/api/v1/auth/refresh", headers=_auth_header(expired))
    assert response.status_code == 200
    assert response.json()["data"]["access_token"] != expired


def test_refresh_without_cookie_returns_401(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == 40100


def test_refresh_route_is_public_and_has_no_current_user_dependency() -> None:
    from app.core.auth_public import is_public_route
    from app.main import app

    assert is_public_route("POST", "/api/v1/auth/refresh")
    assert is_public_route("GET", "/api/v1/health")
    assert is_public_route("GET", "/api/crypto/public-key")
    assert not is_public_route("GET", "/api/v1/auth/me")
    assert not is_public_route("GET", "/api/v1/auth/public-key")

    paths = app.openapi()["paths"]
    assert "/api/v1/auth/refresh" in paths
    assert "post" in paths["/api/v1/auth/refresh"]
    refresh_source = paths["/api/v1/auth/refresh"]["post"]
    assert "get_current_user" not in str(refresh_source)

    import inspect

    from app.api.v1 import auth as auth_module

    parameters = inspect.signature(auth_module.refresh).parameters
    assert "user" not in parameters
    assert "request" in parameters


def test_expired_refresh_token_returns_401(client: TestClient) -> None:
    _register(client)
    login_response = _login(client)
    access_token = login_response.json()["data"]["access_token"]
    me = client.get("/api/v1/auth/me", headers=_auth_header(access_token)).json()["data"]
    expired, jti = create_token(
        user_id=me["id"],
        token_type="refresh",
        expires_delta=timedelta(seconds=-30),
    )
    token_store.save_refresh_session(jti=jti, user_id=me["id"], ttl_seconds=60)
    client.cookies.set(settings.refresh_cookie_name, expired)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == 40103


def test_invalid_refresh_token_returns_401(client: TestClient) -> None:
    client.cookies.set(settings.refresh_cookie_name, "not-a-jwt")
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == 40102


def test_rotated_refresh_cookie_cannot_be_reused(client: TestClient) -> None:
    _register(client)
    login_response = _login(client)
    old_cookie = login_response.cookies.get(settings.refresh_cookie_name)
    assert old_cookie
    first = client.post("/api/v1/auth/refresh")
    assert first.status_code == 200
    client.cookies.set(settings.refresh_cookie_name, old_cookie)
    reused = client.post("/api/v1/auth/refresh")
    assert reused.status_code == 401
    assert reused.json()["code"] == 40104
