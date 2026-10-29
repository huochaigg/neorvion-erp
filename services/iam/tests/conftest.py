"""测试必须使用独立库 neorvion_iam_test。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parents[1] / ".env")
_load_dotenv(Path(__file__).resolve().parents[2] / "erp" / ".env")

os.environ["APP_ENV"] = "test"
os.environ["MYSQL_DATABASE"] = "neorvion_iam_test"
os.environ["MYSQL_TEST_DATABASE"] = "neorvion_iam_test"
os.environ["REDIS_DB"] = "14"
os.environ["JWT_ISSUER"] = "neorvion-iam"
os.environ["JWT_AUDIENCES"] = "neorvion-iam,neorvion-erp,neorvion-knowledge"
os.environ["PERMISSION_SYNC_KEY"] = "iam-test-sync-key"
os.environ["INTERNAL_SERVICE_KEY"] = "iam-test-internal-key"

_ROOT = Path(tempfile.mkdtemp(prefix="neorvion-iam-keys-"))


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


_RSA = _ROOT / "rsa-v1"
_JWT = _ROOT / "jwt-v1"
_write_rsa_pair(_RSA)
_write_rsa_pair(_JWT)

os.environ["RSA_KEY_ID"] = "v1"
os.environ["RSA_PRIVATE_KEY_PATH"] = str(_RSA / "private.pem")
os.environ["RSA_PUBLIC_KEY_PATH"] = str(_RSA / "public.pem")
os.environ["JWT_KEY_ID"] = "jwt-v1"
os.environ["JWT_PRIVATE_KEY_PATH"] = str(_JWT / "private.pem")
os.environ["JWT_PUBLIC_KEY_PATH"] = str(_JWT / "public.pem")

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
        connection.execute(text(f"DROP DATABASE IF EXISTS `{settings.mysql_test_database}`"))
        connection.execute(
            text(
                f"CREATE DATABASE `{settings.mysql_test_database}` "
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


def _wipe() -> None:
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in (
            "audit_logs",
            "authz_outbox",
            "authz_revisions",
            "auth_sessions",
            "menus",
            "role_permissions",
            "member_roles",
            "roles",
            "permissions",
            "applications",
            "tenant_members",
            "tenants",
            "users",
        ):
            session.execute(text(f"DELETE FROM {table}"))
        session.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    _wipe()
    yield
    redis_client.flushdb()
    _wipe()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
