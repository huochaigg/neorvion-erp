"""授权版本与失效 outbox。必须与角色/成员变更写在同一数据库事务里。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthzRevision(Base):
    """每个 (user, tenant) 的授权版本。事务内递增，业务服务高风险路径读 IAM 库。"""

    __tablename__ = "authz_revisions"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_authz_revisions_user_tenant"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AuthzOutbox(Base):
    """授权变更后刷新 Redis 的可靠事件。Pub/Sub 只做加速，本表才是待同步证据。"""

    __tablename__ = "authz_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
