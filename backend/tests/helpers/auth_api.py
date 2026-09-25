from app.core.rsa_crypto import encrypt_with_public_pem
from fastapi.testclient import TestClient

PLAIN_PASSWORD = "Passw0rd!"


def public_key(client: TestClient) -> dict[str, object]:
    response = client.get("/api/crypto/public-key")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def encrypted_fields(client: TestClient, password: str = PLAIN_PASSWORD) -> dict[str, str]:
    material = public_key(client)
    return {
        "encrypted_password": encrypt_with_public_pem(str(material["public_key"]), password),
        "key_id": str(material["key_id"]),
        "challenge_id": str(material["challenge_id"]),
    }


def auth_header(access_token: str, tenant_id: int | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if tenant_id is not None:
        headers["X-Tenant-ID"] = str(tenant_id)
    return headers


def register_and_login(
    client: TestClient,
    email: str,
    display_name: str = "User",
) -> tuple[str, int]:
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": display_name,
            **encrypted_fields(client),
        },
    )
    assert register.status_code == 200, register.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, **encrypted_fields(client)},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    me = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert me.status_code == 200, me.text
    return token, int(me.json()["data"]["id"])
