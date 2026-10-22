from collections.abc import Generator

from app.core.config import settings
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

# 生产请求仍使用普通 Session。租户守卫只挂在 neorvion_db 的会话子类上，
# V1 不替换 SessionLocal，因此现有查询不会被改写。
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """请求级 Session。Repository 不得自行 commit，事务边界放在 Service。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
