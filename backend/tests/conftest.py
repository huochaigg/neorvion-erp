"""测试必须使用独立库 neorvion_erp_test，避免碰到业务库或其他项目。"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["MYSQL_DATABASE"] = "neorvion_erp_test"
os.environ["REDIS_DB"] = "15"

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.core.redis import redis_client
from app.db.session import SessionLocal
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

get_settings.cache_clear()


def _ensure_test_database() -> None:
    settings = get_settings()
    admin_engine = create_engine(settings.build_database_url("mysql"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_test_database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
    admin_engine.dispose()


def _run_migrations() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def setup_test_database() -> Iterator[None]:
    _ensure_test_database()
    _run_migrations()
    yield
    redis_client.flushdb()


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    yield
    redis_client.flushdb()
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM users"))
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
