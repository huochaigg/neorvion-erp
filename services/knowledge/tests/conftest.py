"""测试必须使用独立库 neorvion_knowledge_test，避免碰到业务库。"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from uuid import uuid4


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


_load_dotenv()
os.environ["APP_ENV"] = "test"
os.environ["ERP_JWT_SECRET"] = "knowledge-test-jwt-secret-32bytes!"
os.environ["ERP_INTERNAL_SERVICE_KEY"] = "knowledge-test-internal-key"
os.environ["IDENTITY_CACHE_TTL_SECONDS"] = "30"
if not os.environ.get("TEST_DATABASE_URL"):
    raise RuntimeError("请在 knowledge/.env 或环境变量中设置 TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

import jwt
import pytest
from alembic import command
from alembic.config import Config
from app.api.deps import get_identity_client
from app.core.config import get_settings, settings
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal, get_db
from app.main import app
from app.services.identity import ErpIdentityClient, IdentityCache
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

ALL_KNOWLEDGE_PERMS = frozenset(item.value for item in PermissionCode)
READ_ONLY_PERMS = frozenset({PermissionCode.KNOWLEDGE_READ.value})

get_settings.cache_clear()


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
    yield
    _wipe_tables()


class FakeIdentityClient(ErpIdentityClient):
    """测试用身份源。按 JWT sub + tenant_id 返回预设身份，不访问 ERP。"""

    def __init__(self) -> None:
        super().__init__(cache=IdentityCache())
        self.identities: dict[tuple[int, int], TenantContext] = {}
        self.forbidden: set[tuple[int, int]] = set()
        self.missing: set[tuple[int, int]] = set()

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
        context = TenantContext(
            user_id=user_id,
            tenant_id=tenant_id,
            member_id=member_id or user_id * 10 + tenant_id,
            is_owner=is_owner,
            role=role,
            permission_codes=permissions,
            token_jti="test",
        )
        self.identities[(user_id, tenant_id)] = context
        return context

    async def resolve(self, *, access_token: str, tenant_id: int, jti: str) -> TenantContext:
        from app.core.exceptions import AppError

        payload = jwt.decode(
            access_token,
            settings.erp_jwt_secret,
            algorithms=[settings.erp_jwt_algorithm],
        )
        user_id = int(payload["sub"])
        key = (user_id, tenant_id)
        if key in self.forbidden:
            raise AppError("无权访问该租户", code=40310, status_code=403)
        if key in self.missing:
            raise AppError("租户不存在或不可访问", code=40410, status_code=404)
        context = self.identities.get(key)
        if context is None:
            raise AppError("租户不存在或不可访问", code=40410, status_code=404)
        return TenantContext(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            member_id=context.member_id,
            is_owner=context.is_owner,
            role=context.role,
            permission_codes=context.permission_codes,
            token_jti=jti,
        )


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

    app.dependency_overrides[get_identity_client] = lambda: identity
    app.dependency_overrides[get_db] = _override_db
    with TestClient(app, backend_options=_testclient_backend_options() or {}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.erp_jwt_secret, algorithm=settings.erp_jwt_algorithm)


def auth_header(user_id: int, tenant_id: int | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {make_token(user_id)}"}
    if tenant_id is not None:
        headers["X-Tenant-ID"] = str(tenant_id)
    return headers
