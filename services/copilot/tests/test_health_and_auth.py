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


def test_conversation_detail_declares_get(client) -> None:
    spec = client.get("/openapi.json").json()
    methods = spec["paths"]["/api/v1/conversations/{conversation_id}"]
    assert "get" in methods
    assert methods["get"]["summary"] == "加载会话详情"
    assert "post" in spec["paths"]["/api/v1/conversations/{conversation_id}/messages"]


def test_get_conversation_is_not_method_not_allowed(client) -> None:
    response = client.get("/api/v1/conversations/1")
    assert response.status_code == 401
    assert response.headers.get("allow") is None or "GET" in (response.headers.get("allow") or "")


def test_identity_timeout_returns_explicit_503(client, monkeypatch) -> None:
    async def timeout(_token: str, _tenant_id: int):
        raise TimeoutError

    monkeypatch.setattr("app.api.deps.verify_tenant_access", timeout)
    response = client.get(
        "/api/v1/conversations/1",
        headers={"Authorization": "Bearer placeholder", "X-Tenant-ID": "7"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == 50313
