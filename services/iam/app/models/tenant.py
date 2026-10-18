"""租户与成员。users 是全局身份；本模块只描述「用户属于哪家企业」。"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.models.user import User

if TYPE_CHECKING:
    from app.models.rbac import MemberRoleGrant, Role


class TenantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class MemberStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class MemberRole(StrEnum):
    """成员行上的所有权标记。细粒度权限走 roles / permissions，本列不要删。"""

    OWNER = "OWNER"
    MEMBER = "MEMBER"

class Tenant(TimestampMixin, Base):
    """租户（企业）表"""
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 对外唯一标识用 code，不用企业名称（名称会重复、会改）。
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=TenantStatus.ACTIVE.value,
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # relationship：在 Python 里用 tenant.members 访问成员行。
    # back_populates 必须两边字段名互指，否则 SQLAlchemy 会当成两套独立关系。
    members: Mapped[list["TenantMember"]] = relationship(back_populates="tenant")
    roles: Mapped[list["Role"]] = relationship(back_populates="tenant")


class TenantMember(TimestampMixin, Base):
    """
    用户与租户的多对多关系，中间表。
    UNIQUE(tenant_id, user_id) 禁止同一人重复加入同一租户。
    """

    __tablename__ = "tenant_members"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_members_tenant_user"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_members_tenant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=MemberStatus.ACTIVE.value,
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=MemberRole.MEMBER.value,
    )
    # 企业内展示名。为空时 API 回退 User.display_name，避免改一家企业的称呼影响全局账号。
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    tenant: Mapped[Tenant] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")
    member_roles: Mapped[list["MemberRoleGrant"]] = relationship(
        back_populates="member",
        overlaps="member_roles,role",
    )
