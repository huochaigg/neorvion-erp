from __future__ import annotations

import os
from collections.abc import Iterator

os.environ["APP_ENV"] = "test"
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["IAM_JWKS_URL"] = "http://127.0.0.1:9/.well-known/jwks.json"

import pytest
from app.api.deps import get_tenant_context, get_workflow
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.main import app
from fastapi.testclient import TestClient


def make_context(*, permitted: bool = True, tenant_id: int = 7) -> TenantContext:
    permissions = (
        frozenset({PermissionCode.COPILOT_USE.value}) if permitted else frozenset()
    )
    return TenantContext(
        user_id=11,
        tenant_id=tenant_id,
        member_id=117,
        is_owner=False,
        role="OPERATOR",
        role_codes=("OPERATOR",),
        permission_codes=permissions,
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
    def apply(*, permitted: bool = True, tenant_id: int = 7) -> TenantContext:
        context = make_context(permitted=permitted, tenant_id=tenant_id)

        async def override_context() -> TenantContext:
            return context

        app.dependency_overrides[get_tenant_context] = override_context
        return context

    return apply


@pytest.fixture
def use_workflow():
    def apply(workflow) -> None:
        app.dependency_overrides[get_workflow] = lambda: workflow

    return apply

