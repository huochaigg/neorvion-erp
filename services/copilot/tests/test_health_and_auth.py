from app.api.deps import get_tenant_context
from app.main import app


def test_health_is_public(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "ok",
        "service": "copilot",
        "version": "2.0.0",
        "git_sha": "",
        "identity": "unavailable",
    }


def test_me_returns_verified_tenant_context(client, authorize) -> None:
    authorize()
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["data"]["tenant_id"] == 7
    assert response.json()["data"]["authz_version"] == 3
    assert response.json()["data"]["permissions"] == ["copilot:use"]


def test_chat_requires_authentication(client) -> None:
    response = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 401
    assert response.json()["code"] == 40100


def test_chat_rejects_missing_tenant_header(client) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer placeholder"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 40030


def test_chat_rejects_invalid_tenant_header(client) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer placeholder", "X-Tenant-ID": "other"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 40030


def test_chat_requires_copilot_permission(client, authorize) -> None:
    authorize(permitted=False)
    response = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 403
    assert response.json()["code"] == 40320
    app.dependency_overrides.pop(get_tenant_context, None)
