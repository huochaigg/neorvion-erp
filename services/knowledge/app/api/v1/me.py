from fastapi import APIRouter

from app.api.deps import TenantContextDep
from app.schemas.common import ApiResponse, ok
from app.schemas.identity import MyPermissionsOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get(
    "/permissions",
    response_model=ApiResponse[MyPermissionsOut],
    summary="当前租户 Knowledge 权限快照",
)
async def my_permissions(context: TenantContextDep) -> ApiResponse[MyPermissionsOut]:
    """给前端隐藏按钮。真正的接口授权仍走 require_permission。"""
    roles = [context.role] if context.role else []
    if context.is_owner and "OWNER" not in roles:
        roles = ["OWNER", *roles]
    return ok(
        MyPermissionsOut(
            roles=sorted(set(roles)),
            permissions=sorted(context.permission_codes),
        )
    )
