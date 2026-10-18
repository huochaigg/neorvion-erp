from fastapi.testclient import TestClient

PLAIN_PASSWORD = "Passw0rd!"


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
    """通过测试身份适配器注册并签发 IAM 格式 JWT。"""
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": display_name},
    )
    assert register.status_code == 200, register.text
    login = client.post("/api/v1/auth/login", json={"email": email})
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    me = client.get("/api/v1/auth/me", headers=auth_header(token))
    assert me.status_code == 200, me.text
    return token, int(me.json()["data"]["id"])
