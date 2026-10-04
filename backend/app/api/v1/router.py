from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.brands import router as brand_router
from app.api.v1.health import router as health_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.inventory import sku_router as product_sku_router
from app.api.v1.permissions import router as permission_router
from app.api.v1.product_categories import router as product_category_router
from app.api.v1.products import router as product_router
from app.api.v1.roles import router as role_router
from app.api.v1.tenants import router as tenant_router
from app.api.v1.warehouses import router as warehouse_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
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
