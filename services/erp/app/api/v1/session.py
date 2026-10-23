"""当前请求的租户会话快照。不管理用户或角色，只回传 IAM 已写入的授权。"""

from fastapi import APIRouter

from app.api.deps import TenantContextDep
from app.schemas.common import ApiResponse, ok
from app.schemas.tenant import MyPermissionsOut, TenantContextOut
from app.services.authorization import AuthorizationService

router = APIRouter(tags=["session"])


@router.get(
    "/tenants/current", response_model=ApiResponse[TenantContextOut], summary="当前租户上下文"
)
def current_tenant_context(context: TenantContextDep) -> ApiResponse[TenantContextOut]:
    """需要 X-Tenant-ID。权限编码来自 Redis 快照，不查 IAM。"""
    codes = sorted(AuthorizationService().permission_codes(context))
    return ok(
        TenantContextOut(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            member_id=context.member_id,
            is_owner=context.is_owner,
            role=context.role,
            permission_codes=codes,
        )
    )


@router.get(
    "/tenants/current/my-permissions",
    response_model=ApiResponse[MyPermissionsOut],
    summary="当前成员有效权限",
)
def current_member_permissions(context: TenantContextDep) -> ApiResponse[MyPermissionsOut]:
    """给 ERP 前端生成菜单。真正的接口授权仍走 require_permission。"""
    return ok(AuthorizationService().current_member_access(context))
