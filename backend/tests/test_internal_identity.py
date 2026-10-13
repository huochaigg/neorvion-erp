from __future__ import annotations

from app.core.config import get_settings, settings
from app.core.permissions import PermissionCode
from fastapi.testclient import TestClient

from tests.helpers.auth_api import auth_header, register_and_login

INTERNAL_KEY = "test-internal-service-key"


def _create_tenant(client: TestClient, token: str, name: str, code: str) -> int:
    response = client.post(
        "/api/v1/tenants",
        json={"name": name, "code": code},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["data"]["id"])


def _enable_internal_key(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", INTERNAL_KEY)
    get_settings.cache_clear()
    monkeypatch.setattr(settings, "internal_service_key", INTERNAL_KEY)


def test_introspect_requires_service_key(client: TestClient, monkeypatch) -> None:
    _enable_internal_key(monkeypatch)
    owner, _ = register_and_login(client, "id-key@example.com")
    tenant_id = _create_tenant(client, owner, "IdKey", "id-key")
    missing = client.post(
        "/api/v1/internal/identity/introspect",
        headers=auth_header(owner, tenant_id),
    )
    assert missing.status_code == 403
    assert missing.json()["code"] == 40331
    wrong = client.post(
        "/api/v1/internal/identity/introspect",
        headers={**auth_header(owner, tenant_id), "X-Internal-Service-Key": "wrong"},
    )
    assert wrong.status_code == 403
    assert wrong.json()["code"] == 40331


def test_introspect_returns_identity_and_knowledge_permissions(
    client: TestClient,
    monkeypatch,
) -> None:
    _enable_internal_key(monkeypatch)
    owner, user_id = register_and_login(client, "id-ok@example.com")
    tenant_id = _create_tenant(client, owner, "IdOk", "id-ok")
    response = client.post(
        "/api/v1/internal/identity/introspect",
        headers={
            **auth_header(owner, tenant_id),
            "X-Internal-Service-Key": INTERNAL_KEY,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["user_id"] == user_id
    assert data["tenant_id"] == tenant_id
    assert data["is_owner"] is True
    assert data["token_jti"]
    assert PermissionCode.KNOWLEDGE_READ in data["permission_codes"]
    assert PermissionCode.KNOWLEDGE_CREATE in data["permission_codes"]
    assert PermissionCode.KNOWLEDGE_DELETE in data["permission_codes"]


def test_introspect_unauthenticated(client: TestClient, monkeypatch) -> None:
    _enable_internal_key(monkeypatch)
    response = client.post(
        "/api/v1/internal/identity/introspect",
        headers={"X-Internal-Service-Key": INTERNAL_KEY, "X-Tenant-ID": "1"},
    )
    assert response.status_code == 401
