from collections.abc import AsyncIterator
from typing import cast

from neorvion_db import TenantAsyncSession
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.isolation import REGISTRY

engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.app_env == "development",
)


# 健康检查、API Key 哈希定位和脚本仍用普通 AsyncSession。
# 业务路由使用 TenantAsyncSession，守卫不挂在 AsyncSession 基类上。
SessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """普通异步 Session。健康检查和 Key 定位使用。业务路由不要用它访问租户表。"""
    async with SessionLocal() as session:
        yield session


def _as_async_session(session: object) -> AsyncSession:
    """类型检查器按各自虚拟环境解析 SQLAlchemy，看不到这里的继承关系。"""
    return cast(AsyncSession, session)


def open_tenant_session(tenant_id: int) -> AsyncSession:
    """按已确认的 tenant_id 打开异步租户会话。运行时对象仍是 TenantAsyncSession。"""
    session = TenantAsyncSession(tenant_id, registry=REGISTRY, bind=engine)
    return _as_async_session(session)
