from fastapi import APIRouter

from app.api.v1.after_sales import router as after_sale_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.brands import router as brand_router
from app.api.v1.carriers import router as carrier_router
from app.api.v1.customers import router as customer_router
from app.api.v1.events import router as event_router
from app.api.v1.health import router as health_router
from app.api.v1.internal_identity import router as internal_identity_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.inventory import sku_router as product_sku_router
from app.api.v1.operation_logs import router as operation_log_router
from app.api.v1.outbound_orders import router as outbound_order_router
from app.api.v1.permissions import router as permission_router
from app.api.v1.product_categories import router as product_category_router
from app.api.v1.products import router as product_router
from app.api.v1.purchase_orders import router as purchase_order_router
from app.api.v1.purchase_receipts import router as purchase_receipt_router
from app.api.v1.purchase_return_outbounds import router as purchase_return_outbound_router
from app.api.v1.purchase_returns import router as purchase_return_router
from app.api.v1.refunds import router as refund_router
from app.api.v1.return_orders import router as return_order_router
from app.api.v1.roles import router as role_router
from app.api.v1.sales_orders import router as sales_order_router
from app.api.v1.shipments import router as shipment_router
from app.api.v1.stock_transfers import router as stock_transfer_router
from app.api.v1.stocktakes import router as stocktake_router
from app.api.v1.supplier_refunds import router as supplier_refund_router
from app.api.v1.suppliers import router as supplier_router
from app.api.v1.tasks import router as task_router
from app.api.v1.tenants import router as tenant_router
from app.api.v1.warehouses import router as warehouse_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(internal_identity_router)
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(permission_router)
api_router.include_router(role_router)
api_router.include_router(tenant_router)
api_router.include_router(product_category_router)
api_router.include_router(brand_router)
api_router.include_router(product_router)
api_router.include_router(warehouse_router)
api_router.include_router(inventory_router)
api_router.include_router(product_sku_router)
api_router.include_router(supplier_router)
api_router.include_router(purchase_order_router)
api_router.include_router(purchase_receipt_router)
api_router.include_router(purchase_return_router)
api_router.include_router(purchase_return_outbound_router)
api_router.include_router(supplier_refund_router)
api_router.include_router(customer_router)
api_router.include_router(sales_order_router)
api_router.include_router(outbound_order_router)
api_router.include_router(carrier_router)
api_router.include_router(shipment_router)
api_router.include_router(stocktake_router)
api_router.include_router(stock_transfer_router)
api_router.include_router(after_sale_router)
api_router.include_router(return_order_router)
api_router.include_router(refund_router)
api_router.include_router(analytics_router)
api_router.include_router(event_router)
api_router.include_router(operation_log_router)
api_router.include_router(task_router)
