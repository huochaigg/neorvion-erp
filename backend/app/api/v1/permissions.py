from fastapi import APIRouter

from app.api.deps import DbSession
from app.api.rbac_deps import RoleReadContext
from app.schemas.common import ApiResponse, ok
from app.schemas.rbac import PermissionOut
from app.services.rbac import RoleService

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("", response_model=ApiResponse[list[PermissionOut]], summary="平台权限目录")
def list_permissions(
    context: RoleReadContext,
    session: DbSession,
) -> ApiResponse[list[PermissionOut]]:
    """需要有效租户上下文。目录是平台统一定义，不是某家企业私有的。"""
    return ok(RoleService(session).list_permissions(context))
