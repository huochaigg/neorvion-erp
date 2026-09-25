import pytest
from app.schemas.health import HealthCheckData
from app.services.health import HealthService
from fastapi.testclient import TestClient


def test_openapi_includes_health(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/health" in response.json()["paths"]


def test_health_response_shape(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["app"] == "ok"
    assert body["data"]["milestone"] == "M1"
    assert body["data"]["mysql"] in {"ok", "unavailable"}
    assert body["data"]["redis"] in {"ok", "unavailable"}


def test_health_service_marks_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummySession:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("db down")

    monkeypatch.setattr("app.services.health.ping_redis", lambda: False)
    data: HealthCheckData = HealthService(DummySession()).check()  # type: ignore[arg-type]
    assert data.mysql == "unavailable"
    assert data.redis == "unavailable"
