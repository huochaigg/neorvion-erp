"""ORM 模型。Alembic 通过导入本包收集 metadata。"""

from app.db.base import Base
from app.models.action_execution import ErpActionExecutionReceipt
from app.models.after_sale import (
    AFTER_SALE_REFERENCE,
    AfterSaleItem,
    AfterSaleOrder,
    AfterSaleStatus,
    AfterSaleType,
    RefundStatus,
)
from app.models.async_task import AsyncTask, AsyncTaskLog
from app.models.carrier import Carrier, CarrierStatus, CarrierType
from app.models.customer import Customer, CustomerStatus
from app.models.identity import IdentityNameSnapshot
from app.models.inventory import Inventory, InventoryTransaction, InventoryTransactionType
from app.models.operation_log import OperationLog
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
from app.models.purchase_return import (
    PURCHASE_RETURN_REFERENCE,
    PurchaseReturn,
    PurchaseReturnItem,
    PurchaseReturnRefundStatus,
    PurchaseReturnSettlementType,
    PurchaseReturnStatus,
)
from app.models.purchase_return_outbound import (
    PURCHASE_RETURN_OUTBOUND_REFERENCE,
    PurchaseReturnOutbound,
    PurchaseReturnOutboundItem,
    PurchaseReturnOutboundStatus,
)
from app.models.refund import REFUND_REFERENCE, RefundRecord, RefundRecordStatus
from app.models.return_order import (
    RETURN_ORDER_REFERENCE,
    ReturnCondition,
    ReturnOrder,
    ReturnOrderItem,
    ReturnOrderStatus,
)
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
from app.models.stock_transfer import (
    STOCK_TRANSFER_REFERENCE,
    StockTransfer,
    StockTransferItem,
    StockTransferStatus,
)
from app.models.stocktake import (
    STOCKTAKE_REFERENCE,
    StocktakeItem,
    StocktakeOrder,
    StocktakeOrderStatus,
    StocktakeScope,
)
from app.models.supplier import Supplier, SupplierStatus
from app.models.supplier_refund import (
    SUPPLIER_REFUND_REFERENCE,
    SupplierRefundRecord,
    SupplierRefundRecordStatus,
)
from app.models.system_event import SystemEvent
from app.models.tenant import MemberRole, MemberStatus, TenantStatus
from app.models.warehouse import Warehouse, WarehouseStatus, WarehouseType

__all__ = [
    "AFTER_SALE_REFERENCE",
    "AfterSaleItem",
    "AfterSaleOrder",
    "AfterSaleStatus",
    "AfterSaleType",
    "AsyncTask",
    "AsyncTaskLog",
    "ErpActionExecutionReceipt",
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
    "IdentityNameSnapshot",
    "MemberRole",
    "MemberStatus",
    "OutboundOrder",
    "OutboundOrderItem",
    "OutboundOrderStatus",
    "OutboundPick",
    "OutboundPickLine",
    "OperationLog",
    "Product",
    "ProductCategory",
    "ProductSku",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseOrderStatus",
    "PURCHASE_RETURN_OUTBOUND_REFERENCE",
    "PURCHASE_RETURN_REFERENCE",
    "PurchaseReceipt",
    "PurchaseReceiptItem",
    "PurchaseReceiptStatus",
    "PurchaseReturn",
    "PurchaseReturnItem",
    "PurchaseReturnOutbound",
    "PurchaseReturnOutboundItem",
    "PurchaseReturnOutboundStatus",
    "PurchaseReturnRefundStatus",
    "PurchaseReturnSettlementType",
    "PurchaseReturnStatus",
    "SUPPLIER_REFUND_REFERENCE",
    "SupplierRefundRecord",
    "SupplierRefundRecordStatus",
    "REFUND_REFERENCE",
    "RETURN_ORDER_REFERENCE",
    "RefundRecord",
    "RefundRecordStatus",
    "RefundStatus",
    "ReturnCondition",
    "ReturnOrder",
    "ReturnOrderItem",
    "ReturnOrderStatus",
    "SALES_ORDER_REFERENCE",
    "SalesOrder",
    "SalesOrderItem",
    "SalesOrderSource",
    "SalesOrderStatus",
    "Shipment",
    "ShipmentItem",
    "ShipmentStatus",
    "ShipmentTrackingEvent",
    "STOCK_TRANSFER_REFERENCE",
    "STOCKTAKE_REFERENCE",
    "StockTransfer",
    "StockTransferItem",
    "StockTransferStatus",
    "StocktakeItem",
    "StocktakeOrder",
    "StocktakeOrderStatus",
    "StocktakeScope",
    "TrackingEventStatus",
    "Supplier",
    "SupplierStatus",
    "SystemEvent",
    "TenantStatus",
    "Warehouse",
    "WarehouseStatus",
    "WarehouseType",
]
