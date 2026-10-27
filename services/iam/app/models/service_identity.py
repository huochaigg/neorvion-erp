from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ServiceIdentity(Base):
    """后台服务主体。凭据只保存 Argon2 哈希，授权范围使用显式白名单。"""

    __tablename__ = "service_identities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="SERVICE")
    tenant_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    allowed_audiences: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allowed_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allowed_resources: Mapped[dict] = mapped_column(JSON, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ACTIVE")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ServiceIdentityAudit(Base):
    """服务身份安全审计。不记录 Token、Secret 或业务载荷。"""

    __tablename__ = "service_identity_audits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    service_identity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("service_identities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    token_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    safe_detail: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
