from typing import Annotated

from fastapi import Depends

from app.api.deps import DbSession, TenantContextDep
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.services.authorization import AuthorizationService


def require_permission(*codes: str):
    """当前成员必须拥有列出的全部权限。

    FastAPI 会先走 TenantContextDep（登录 + X-Tenant-ID + 成员有效），
    再查库汇总角色权限。不要把 JWT 或请求体里的角色列表当成授权依据。
    """

    def dependency(context: TenantContextDep, session: DbSession) -> TenantContext:
        AuthorizationService(session).require_all(context, codes)
        return context

    return dependency


def require_all_permissions(*codes: str):
    return require_permission(*codes)


def require_any_permission(*codes: str):
    def dependency(context: TenantContextDep, session: DbSession) -> TenantContext:
        AuthorizationService(session).require_any(context, codes)
        return context

    return dependency


RoleReadContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_ROLE_READ)),
]
RoleCreateContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_ROLE_CREATE)),
]
RoleUpdateContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_ROLE_UPDATE)),
]
RoleDeleteContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_ROLE_DELETE)),
]
RolePermissionUpdateContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_ROLE_PERMISSION_UPDATE)),
]
PermissionCatalogContext = Annotated[
    TenantContext,
    Depends(
        require_any_permission(
            PermissionCode.TENANT_PERMISSION_READ,
            PermissionCode.TENANT_ROLE_READ,
            PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,
        )
    ),
]
MemberReadContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_MEMBER_READ)),
]
MemberCreateContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_MEMBER_CREATE)),
]
MemberUpdateContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_MEMBER_UPDATE)),
]
MemberRoleUpdateContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_MEMBER_ROLE_UPDATE)),
]
MemberDisableContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_MEMBER_DISABLE)),
]
MemberRemoveContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.TENANT_MEMBER_REMOVE)),
]
