from typing import cast

from neorvion_db import TenantAsyncSession
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.db.isolation import REGISTRY

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout_seconds,
    pool_recycle=1800,
    pool_use_lifo=True,
    connect_args={
        "connect_timeout": settings.database_connect_timeout_seconds,
        "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
    },
)


def open_tenant_session(tenant_id: int) -> AsyncSession:
    return cast(
        AsyncSession,
        TenantAsyncSession(
            tenant_id,
            registry=REGISTRY,
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        ),
    )


async def close_database() -> None:
    await engine.dispose()
