"""测试必须使用独立库 neorvion_knowledge_test，避免碰到业务库。"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _load_dotenv() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_JWT_ROOT = Path(tempfile.mkdtemp(prefix="neorvion-knowledge-jwt-"))
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
(_JWT_ROOT / "private.pem").write_bytes(
    _key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
)
(_JWT_ROOT / "public.pem").write_bytes(
    _key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
)

_load_dotenv()
os.environ["APP_ENV"] = "test"
os.environ["IAM_JWT_ISSUER"] = "neorvion-iam"
os.environ["IAM_JWT_AUDIENCE"] = "neorvion-knowledge"
os.environ["IAM_JWKS_URL"] = ""
os.environ["IAM_JWT_KEY_ID"] = "jwt-v1"
os.environ["IAM_JWT_PRIVATE_KEY_PATH"] = str(_JWT_ROOT / "private.pem")
os.environ["IAM_JWT_PUBLIC_KEY_PATH"] = str(_JWT_ROOT / "public.pem")
os.environ["IAM_REDIS_URL"] = os.environ.get("IAM_REDIS_URL", "redis://127.0.0.1:6379/13")
os.environ["TASK_EXECUTOR"] = "inline"
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["EMBEDDING_DIMENSIONS"] = "8"
os.environ["EMBEDDING_MODEL"] = "mock-embed"
os.environ["CHAT_MODEL"] = "mock-chat"
os.environ.setdefault("STORAGE_ROOT", str(Path(__file__).resolve().parents[1] / "var" / "test-storage"))
if not os.environ.get("TEST_DATABASE_URL"):
    raise RuntimeError("请在 knowledge/.env 或环境变量中设置 TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import get_settings, settings
from app.core.iam import iam_redis_client, jwt_verifier, snapshot_store, test_signer
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal, get_db
from app.main import app
from fastapi.testclient import TestClient
from neorvion_security import AuthzSnapshot
from sqlalchemy import create_engine, text

ALL_KNOWLEDGE_PERMS = frozenset(item.value for item in PermissionCode)
READ_ONLY_PERMS = frozenset({PermissionCode.KNOWLEDGE_READ.value})

get_settings.cache_clear()
jwt_verifier.cache_clear()
snapshot_store.cache_clear()
test_signer.cache_clear()


def _admin_database_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path="/postgres"))


def _ensure_test_database() -> None:
    admin_engine = create_engine(
        _admin_database_url(settings.test_database_url),
        isolation_level="AUTOCOMMIT",
    )
    db_name = urlparse(settings.test_database_url).path.lstrip("/")
    with admin_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()


def _run_migrations() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")


def _wipe_tables() -> None:
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM evaluation_results"))
        connection.execute(text("DELETE FROM evaluation_runs"))
        connection.execute(text("DELETE FROM evaluation_experiments"))
        connection.execute(text("DELETE FROM evaluation_judgments"))
        connection.execute(text("DELETE FROM evaluation_cases"))
        connection.execute(text("DELETE FROM evaluation_dataset_versions"))
        connection.execute(text("DELETE FROM evaluation_datasets"))
        connection.execute(text("DELETE FROM message_citations"))
        connection.execute(text("DELETE FROM messages"))
        connection.execute(text("DELETE FROM conversations"))
        connection.execute(text("DELETE FROM retrieval_logs"))
        connection.execute(text("DELETE FROM chunk_embeddings"))
        connection.execute(text("DELETE FROM model_profiles"))
        connection.execute(text("DELETE FROM knowledge_audit_logs"))
        connection.execute(text("DELETE FROM knowledge_api_keys"))
        connection.execute(text("DELETE FROM knowledge_base_grants"))
        connection.execute(text("DELETE FROM document_revisions"))
        connection.execute(text("DELETE FROM document_chunks"))
        connection.execute(text("DELETE FROM document_processing_tasks"))
        connection.execute(text("DELETE FROM knowledge_documents"))
        connection.execute(text("DELETE FROM knowledge_bases"))
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database() -> Iterator[None]:
    _ensure_test_database()
    _run_migrations()
    yield


@pytest.fixture(autouse=True)
def clean_state() -> Iterator[None]:
    _wipe_tables()
    iam_redis_client.flushdb()
    yield
    iam_redis_client.flushdb()
    _wipe_tables()


class FakeIdentityClient:
    """测试用身份源。把 grant 写入 IAM Redis 快照，供 JwtVerifier 本地校验。"""

    def grant(
        self,
        user_id: int,
        tenant_id: int,
        *,
        permissions: frozenset[str] = ALL_KNOWLEDGE_PERMS,
        role: str = "OWNER",
        is_owner: bool = True,
        member_id: int | None = None,
    ) -> TenantContext:
        snapshot = AuthzSnapshot(
            user_id=user_id,
            tenant_id=tenant_id,
            member_id=member_id or user_id * 10 + tenant_id,
            is_owner=is_owner,
            role=role,
            status="ACTIVE",
            tenant_status="ACTIVE",
            permission_codes=tuple(sorted(permissions)),
            role_codes=(role,),
            authz_version=1,
            token_version=0,
            display_name=f"User{user_id}",
            email=f"user{user_id}@test.local",
        )
        snapshot_store().save(snapshot)
        return snapshot.to_context(token_jti="test")


@pytest.fixture
def identity() -> FakeIdentityClient:
    return FakeIdentityClient()


def _testclient_backend_options() -> dict[str, object] | None:
    """Windows 上 psycopg 异步驱动无法使用 ProactorEventLoop。"""
    if sys.platform != "win32":
        return None
    return {"loop_factory": asyncio.SelectorEventLoop}


@pytest.fixture
def client(identity: FakeIdentityClient) -> Iterator[TestClient]:
    async def _override_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app, backend_options=_testclient_backend_options() or {}) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    iam_redis_client.flushdb()


def make_token(user_id: int) -> str:
    token, _jti = test_signer().sign(
        user_id=user_id,
        token_type="access",
        ttl=timedelta(minutes=30),
        token_version=0,
    )
    return token


def auth_header(user_id: int, tenant_id: int | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {make_token(user_id)}"}
    if tenant_id is not None:
        headers["X-Tenant-ID"] = str(tenant_id)
    return headers
