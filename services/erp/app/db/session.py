from collections.abc import Generator
from typing import cast

from neorvion_db import GlobalIdentityPurpose, GlobalIdentitySession, TenantSession
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.isolation import REGISTRY

engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.app_env == "development",
)

# 健康检查、脚本、迁移和直接构造的测试会话仍用普通 Session。
# 业务路由走 get_tenant_db，不把守卫挂到 Session 基类上。
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """普通 Session。健康检查和脚本使用。业务路由不要用它访问租户表。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _as_session(session: object) -> Session:
    """类型检查器按各自虚拟环境解析 SQLAlchemy，看不到这里的继承关系。"""
    return cast(Session, session)


def open_identity_session() -> Session:
    """展示名投影会话。不读取租户上下文，避免和租户会话互相依赖。"""
    session = GlobalIdentitySession(
        GlobalIdentityPurpose.DISPLAY_PROJECTION,
        registry=REGISTRY,
        bind=engine,
    )
    return _as_session(session)


def open_tenant_session(tenant_id: int) -> Session:
    """按已认证的 tenant_id 打开业务会话。调用方必须先完成成员校验。"""
    session = TenantSession(tenant_id, registry=REGISTRY, bind=engine)
    return _as_session(session)
