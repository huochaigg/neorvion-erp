from __future__ import annotations

from app.api.deps import get_db
from app.main import app
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError


def test_pool_timeout_returns_explicit_503(client, authorize) -> None:
    authorize()

    async def exhausted_pool():
        raise SqlAlchemyTimeoutError("pool exhausted")

    app.dependency_overrides[get_db] = exhausted_pool
    response = client.get("/api/v1/conversations/1")
    assert response.status_code == 503
    assert response.json() == {
        "code": 50380,
        "message": "会话数据库连接繁忙，请稍后重试",
        "data": None,
    }


def test_database_unavailable_returns_explicit_503(client, authorize) -> None:
    authorize()

    async def unavailable_database():
        raise OperationalError("connect", {}, ConnectionError("unavailable"))

    app.dependency_overrides[get_db] = unavailable_database
    response = client.get("/api/v1/conversations/1")
    assert response.status_code == 503
    assert response.json() == {
        "code": 50381,
        "message": "会话数据库暂时不可用",
        "data": None,
    }
