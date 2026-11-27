import pytest
from fastapi import Request
from fastapi.routing import APIRoute
from neorvion_security import SecurityError

from app.api.deps import get_tenant_context
from app.api.v1.conversations import router
from app.core.exceptions import AppError


def _has_dependency(dependant, function) -> bool:
    return any(
        dependency.call is function or _has_dependency(dependency, function)
        for dependency in dependant.dependencies
    )


def test_expired_token_is_rejected_by_chat_auth_dependency_before_handler(monkeypatch) -> None:
    route = next(
        item for item in router.routes
        if isinstance(item, APIRoute) and item.path.endswith("/{conversation_id}/messages")
    )
    assert _has_dependency(route.dependant, get_tenant_context)
    calls = []

    async def expired(_token: str, _tenant_id: int):
        calls.append("verify")
        raise SecurityError("expired", code=40103, status_code=401)

    monkeypatch.setattr("app.api.deps.verify_tenant_access", expired)
    request = Request({
        "type": "http", "method": "POST", "path": route.path,
        "headers": [(b"authorization", b"Bearer expired"), (b"x-tenant-id", b"7")],
    })
    with pytest.raises(AppError) as failure:
        get_tenant_context(request).send(None)
    assert (failure.value.status_code, failure.value.code) == (401, 40103)
    assert calls == ["verify"]
