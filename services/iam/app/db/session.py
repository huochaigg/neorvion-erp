from collections.abc import Generator
from typing import cast

from app.core.config import settings
from app.db.isolation import REGISTRY
from neorvion_db import GlobalIdentityPurpose, GlobalIdentitySession, TenantSession
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.app_env == "development",
)

# 健康检查、创建租户、内部授权和高风险回源仍用普通 Session。
# 这些事务要同时写全局表和租户表，不能拆成两种会话。
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """普通 Session。创建租户、我的租户列表、内部授权和平台审计使用。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _as_session(session: object) -> Session:
    """类型检查器按各自虚拟环境解析 SQLAlchemy，看不到这里的继承关系。"""
    return cast(Session, session)


def open_identity_session() -> Session:
    """登录用户、登录会话和平台目录。不能查询租户业务表。"""
    session = GlobalIdentitySession(
        GlobalIdentityPurpose.IAM_DIRECTORY,
        registry=REGISTRY,
        bind=engine,
    )
    return _as_session(session)


def open_tenant_session(tenant_id: int) -> Session:
    """已校验成员资格后的租户会话。"""
    session = TenantSession(tenant_id, registry=REGISTRY, bind=engine)
    return _as_session(session)
