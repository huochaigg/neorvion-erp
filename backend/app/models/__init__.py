"""ORM 模型。Alembic 通过导入本包收集 metadata。"""

from app.db.base import Base
from app.models.carrier import Carrier, CarrierStatus, CarrierType
from app.models.customer import Customer, CustomerStatus
from app.models.inventory import Inventory, InventoryTransaction, InventoryTransactionType
from app.models.outbound import (
    OutboundOrder,
    OutboundOrderItem,
    OutboundOrderStatus,
    OutboundPick,
    OutboundPickLine,
)
from app.models.product import Brand, Product, ProductCategory, ProductSku
from app.models.purchase import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus
from app.models.purchase_receipt import PurchaseReceipt, PurchaseReceiptItem, PurchaseReceiptStatus
from app.models.rbac import MemberRoleGrant, Permission, Role, RolePermission
from app.models.sales_order import (
    SALES_ORDER_REFERENCE,
    SalesOrder,
    SalesOrderItem,
    SalesOrderSource,
    SalesOrderStatus,
)
from app.models.shipment import (
    Shipment,
    ShipmentItem,
    ShipmentStatus,
    ShipmentTrackingEvent,
    TrackingEventStatus,
)
from app.models.supplier import Supplier, SupplierStatus
from app.models.tenant import MemberRole, MemberStatus, Tenant, TenantMember, TenantStatus
from app.models.user import User, UserStatus
from app.models.warehouse import Warehouse, WarehouseStatus, WarehouseType

__all__ = [
    "Base",
    "Brand",
    "Carrier",
    "CarrierStatus",
    "CarrierType",
    "Customer",
    "CustomerStatus",
    "Inventory",
    "InventoryTransaction",
    "InventoryTransactionType",
    "MemberRole",
    "MemberRoleGrant",
    "MemberStatus",
    "OutboundOrder",
    "OutboundOrderItem",
    "OutboundOrderStatus",
    "OutboundPick",
    "OutboundPickLine",
    "Permission",
    "Product",
    "ProductCategory",
    "ProductSku",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseOrderStatus",
    "PurchaseReceipt",
    "PurchaseReceiptItem",
    "PurchaseReceiptStatus",
    "Role",
    "RolePermission",
    "SALES_ORDER_REFERENCE",
    "SalesOrder",
    "SalesOrderItem",
    "SalesOrderSource",
    "SalesOrderStatus",
    "Shipment",
    "ShipmentItem",
    "ShipmentStatus",
    "ShipmentTrackingEvent",
    "TrackingEventStatus",
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
