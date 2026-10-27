"""应用注册、菜单与审计。权限目录仍在 permissions 表，这里只描述系统与菜单树。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Application(TimestampMixin, Base):
    """可注册的业务系统。不硬编码仅 ERP / Knowledge。"""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    audience: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ACTIVE")
    description: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")

    menus: Mapped[list["Menu"]] = relationship(back_populates="application")


class Menu(TimestampMixin, Base):
    """系统菜单 / 按钮。管理员配置优先，业务同步不得覆盖 locked 行。"""

    __tablename__ = "menus"
    __table_args__ = (UniqueConstraint("application_id", "menu_key", name="uq_menus_app_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    menu_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    menu_type: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    permission_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    application: Mapped[Application] = relationship(back_populates="menus")


class AuditLog(Base):
    """身份与权限审计。tenant_id 为空表示平台级操作。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    actor_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
