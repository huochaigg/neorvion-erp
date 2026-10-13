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
    assert body["data"]["app"] == "ok"
    assert body["data"]["milestone"] == "Knowledge V2"
    assert body["data"]["postgres"] in {"ok", "unavailable"}
    assert body["data"]["pgvector"] in {"ok", "unavailable", "not_installed"}
    assert body["data"]["identity"] in {"ok", "unavailable"}
