from __future__ import annotations

import os
from collections.abc import Iterator

os.environ["APP_ENV"] = "test"
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["IAM_JWKS_URL"] = "http://127.0.0.1:9/.well-known/jwks.json"

import pytest
from app.api.deps import get_tenant_context, get_workflow
from app.core.config import settings
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.main import app
from fastapi import Request
from fastapi.testclient import TestClient


def make_context(
    *, permitted: bool = True, tenant_id: int = 7, extra_permissions: set[str] | None = None
) -> TenantContext:
    permissions = set(extra_permissions or ())
    if permitted:
        permissions.add(PermissionCode.COPILOT_USE.value)
    return TenantContext(
        user_id=11,
        tenant_id=tenant_id,
        member_id=117,
        is_owner=False,
        role="OPERATOR",
        role_codes=("OPERATOR",),
        permission_codes=frozenset(permissions),
        token_jti="test-jti",
        token_version=0,
        authz_version=3,
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr("app.api.v1.health.ping_iam_store", lambda: False)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def authorize():
    def apply(
        *, permitted: bool = True, tenant_id: int = 7, extra_permissions: set[str] | None = None
    ) -> TenantContext:
        context = make_context(
            permitted=permitted, tenant_id=tenant_id, extra_permissions=extra_permissions
        )

        async def override_context(request: Request) -> TenantContext:
            request.state.access_token = "test-user-token"
            request.state.jwt_audiences = (settings.erp_jwt_audience,)
            return context

        app.dependency_overrides[get_tenant_context] = override_context
        return context

    return apply


@pytest.fixture
def use_workflow():
    def apply(workflow) -> None:
        app.dependency_overrides[get_workflow] = lambda: workflow

    return apply
