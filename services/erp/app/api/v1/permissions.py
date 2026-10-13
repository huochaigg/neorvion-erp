from fastapi import APIRouter

from app.api.deps import DbSession
from app.api.rbac_deps import PermissionCatalogContext
from app.schemas.common import ApiResponse, ok
from app.schemas.rbac import PermissionOut, PermissionTreeNodeOut
from app.services.rbac import RoleService

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("", response_model=ApiResponse[list[PermissionOut]], summary="平台权限目录")
def list_permissions(
    context: PermissionCatalogContext,
    session: DbSession,
) -> ApiResponse[list[PermissionOut]]:
    """需要有效租户上下文。目录是平台统一定义，不是某家企业私有的。"""
    return ok(RoleService(session).list_permissions(context))


@router.get(
    "/tree",
    response_model=ApiResponse[list[PermissionTreeNodeOut]],
    summary="菜单与按钮权限树",
)
def list_permission_tree(
    context: PermissionCatalogContext,
    session: DbSession,
) -> ApiResponse[list[PermissionTreeNodeOut]]:
    """程序定义的 DIRECTORY / MENU / ACTION 树。只用于配置 UI，最终仍写入 role_permissions。"""
    return ok(RoleService(session).list_permission_tree(context))
