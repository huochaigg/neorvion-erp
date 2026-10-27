"""ORM 模型。Alembic 通过导入本包收集 metadata。"""

from app.db.base import Base
from app.models.authz import AuthzOutbox, AuthzRevision
from app.models.catalog import Application, AuditLog, Menu
from app.models.rbac import MemberRoleGrant, Permission, Role, RolePermission
from app.models.service_identity import ServiceIdentity, ServiceIdentityAudit
from app.models.session import AuthSession
from app.models.tenant import MemberRole, MemberStatus, Tenant, TenantMember, TenantStatus
from app.models.user import User, UserStatus

__all__ = [
    "Application",
    "AuditLog",
    "AuthSession",
    "AuthzOutbox",
    "AuthzRevision",
    "Base",
    "MemberRole",
    "MemberRoleGrant",
    "MemberStatus",
    "Menu",
    "Permission",
    "Role",
    "RolePermission",
    "ServiceIdentity",
    "ServiceIdentityAudit",
    "Tenant",
    "TenantMember",
    "TenantStatus",
    "User",
    "UserStatus",
]
