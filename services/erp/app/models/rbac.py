"""RBAC 表。

User（全局人）→ TenantMember（这家企业的员工）
  → MemberRoleGrant → Role（这家企业的角色）
  → RolePermission → Permission（平台权限目录）。

角色必须带 tenant_id：Acme 的 ADMIN 不能授给 Beta 的员工。
权限不带 tenant_id：tenant:member:manage 对所有企业含义相同，避免每家企业复制一份目录。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant, TenantMember


class Permission(Base):
    """平台统一权限目录。V2.3 不开放租户自建任意 code。"""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    role_permissions: Mapped[list["RolePermission"]] = relationship(back_populates="permission")


class Role(TimestampMixin, Base):
    """租户内的角色。UNIQUE(tenant_id, code) 保证同一企业角色编码不重复。"""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_roles_tenant_code"),
        # 供 member_roles / role_permissions 做复合外键，挡住跨租户乱关联。
        UniqueConstraint("tenant_id", "id", name="uq_roles_tenant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    tenant: Mapped["Tenant"] = relationship(back_populates="roles")
    member_roles: Mapped[list["MemberRoleGrant"]] = relationship(
        back_populates="role",
        overlaps="member,member_roles",
    )
    role_permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role")


class MemberRoleGrant(Base):
    """成员与角色的中间表。显式模型而不是 secondary=，因为有 tenant_id 约束。"""

    __tablename__ = "member_roles"
    __table_args__ = (
        UniqueConstraint("member_id", "role_id", name="uq_member_roles_member_role"),
        ForeignKeyConstraint(
            ["tenant_id", "member_id"],
            ["tenant_members.tenant_id", "tenant_members.id"],
            name="fk_member_roles_member_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_member_roles_role_tenant",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    member_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    member: Mapped["TenantMember"] = relationship(
        back_populates="member_roles",
        overlaps="member_roles,role",
    )
    role: Mapped[Role] = relationship(
        back_populates="member_roles",
        overlaps="member,member_roles",
    )


class RolePermission(Base):
    """角色与权限的中间表。permission 是全局的，所以只对 role 做租户复合外键。"""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_perm"),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            name="fk_role_permissions_role_tenant",
        ),
        ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    permission_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    role: Mapped[Role] = relationship(back_populates="role_permissions")
    permission: Mapped[Permission] = relationship(back_populates="role_permissions")
