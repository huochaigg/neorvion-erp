"""持久化登录会话。只存 Refresh jti 的哈希，不存明文 Refresh Token。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthSession(Base):
    """一次登录设备会话。Refresh 轮换共用 family_id；重放则整族撤销。"""

    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("public_id", name="uq_auth_sessions_public_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    family_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    refresh_jti_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    previous_jti_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoke_reason: Mapped[str] = mapped_column(String(32), nullable=False, server_default="")
