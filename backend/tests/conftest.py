"""测试必须使用独立库 neorvion_erp_test，避免碰到业务库或其他项目。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

os.environ["APP_ENV"] = "test"
os.environ["MYSQL_DATABASE"] = "neorvion_erp_test"
os.environ["REDIS_DB"] = "15"

_RSA_ROOT = Path(tempfile.mkdtemp(prefix="neorvion-rsa-"))


def _write_rsa_pair(directory: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "private.pem").write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (directory / "public.pem").write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


_CURRENT = _RSA_ROOT / "v1"
_PREVIOUS = _RSA_ROOT / "v0"
_write_rsa_pair(_CURRENT)
_write_rsa_pair(_PREVIOUS)

os.environ["RSA_KEY_ID"] = "v1"
os.environ["RSA_PRIVATE_KEY_PATH"] = str(_CURRENT / "private.pem")
os.environ["RSA_PUBLIC_KEY_PATH"] = str(_CURRENT / "public.pem")
os.environ["RSA_PREVIOUS_KEY_ID"] = "v0"
os.environ["RSA_PREVIOUS_PRIVATE_KEY_PATH"] = str(_PREVIOUS / "private.pem")
os.environ["RSA_CHALLENGE_TTL_SECONDS"] = "300"

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
        session.execute(text("DELETE FROM tenant_members"))
        session.execute(text("DELETE FROM tenants"))
        session.execute(text("DELETE FROM users"))
        session.commit()
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
