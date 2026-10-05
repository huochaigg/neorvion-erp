"""ORM 模型。Alembic 通过导入本包收集 metadata。"""

from app.db.base import Base
from app.models.inventory import Inventory, InventoryTransaction, InventoryTransactionType
from app.models.product import Brand, Product, ProductCategory, ProductSku
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.rbac import MemberRoleGrant, Permission, Role, RolePermission
from app.models.supplier import Supplier, SupplierStatus
from app.models.tenant import MemberRole, MemberStatus, Tenant, TenantMember, TenantStatus
from app.models.user import User, UserStatus
from app.models.warehouse import Warehouse, WarehouseStatus, WarehouseType

__all__ = [
    "Base",
    "Brand",
    "Inventory",
    "InventoryTransaction",
    "InventoryTransactionType",
    "MemberRole",
    "MemberRoleGrant",
    "MemberStatus",
    "Permission",
    "Product",
    "ProductCategory",
    "ProductSku",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseOrderStatus",
    "Role",
    "RolePermission",
    "Supplier",
    "SupplierStatus",
    "Tenant",
    "TenantMember",
    "TenantStatus",
    "User",
    "UserStatus",
    "Warehouse",
    "WarehouseStatus",
    "WarehouseType",
]
