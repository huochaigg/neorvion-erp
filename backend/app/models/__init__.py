"""ORM 模型。Alembic 通过导入本包收集 metadata。"""

from app.db.base import Base
from app.models.product import Brand, Product, ProductCategory, ProductSku
from app.models.rbac import MemberRoleGrant, Permission, Role, RolePermission
from app.models.tenant import MemberRole, MemberStatus, Tenant, TenantMember, TenantStatus
from app.models.user import User, UserStatus

__all__ = [
    "Base",
    "Brand",
    "MemberRole",
    "MemberRoleGrant",
    "MemberStatus",
    "Permission",
    "Product",
    "ProductCategory",
    "ProductSku",
    "Role",
    "RolePermission",
    "Tenant",
    "TenantMember",
    "TenantStatus",
    "User",
    "UserStatus",
]
