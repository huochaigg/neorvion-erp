from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.health import router as health_router
from app.api.v1.internal import router as internal_router
from app.api.v1.permissions import router as permission_router
from app.api.v1.roles import router as role_router
from app.api.v1.service_identities import router as service_identity_router
from app.api.v1.sessions import router as session_router
from app.api.v1.tenants import router as tenant_router
from app.api.v1.users import router as user_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(session_router)
api_router.include_router(service_identity_router)
api_router.include_router(internal_router)
api_router.include_router(permission_router)
api_router.include_router(role_router)
api_router.include_router(tenant_router)
api_router.include_router(user_router)
api_router.include_router(catalog_router)
