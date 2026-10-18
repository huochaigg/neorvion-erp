from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, TenantContextDep
from app.api.rbac_deps import (
    MemberCreateContext,
    MemberReadContext,
    MemberRemoveContext,
    MemberRoleUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.tenant import (
    MemberAccountCreate,
    MemberCreate,
    MemberCreatedOut,
    MemberDetailOut,
    MemberListOut,
    MemberOut,
    MemberRolesUpdate,
    MemberUpdate,
    MyPermissionsOut,
    TenantContextOut,
    TenantCreate,
    TenantOut,
)
from app.services.authorization import AuthorizationService
from app.services.tenant import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=ApiResponse[TenantOut], summary="创建租户")
def create_tenant(
    payload: TenantCreate,
    user: CurrentUser,
    session: DbSession,
) -> ApiResponse[TenantOut]:
    """登录用户创建企业，并在同一事务中把自己写成 OWNER。不要求 X-Tenant-ID。"""
    tenant = TenantService(session).create_tenant(
        user=user,
        name=payload.name,
        code=payload.code,
    )
    return ok(tenant, "创建成功")


@router.get("", response_model=ApiResponse[list[TenantOut]], summary="我的租户")
def list_tenants(user: CurrentUser, session: DbSession) -> ApiResponse[list[TenantOut]]:
    """只返回当前 JWT 用户加入过的企业。"""
    return ok(TenantService(session).list_my_tenants(user))


@router.get("/current", response_model=ApiResponse[TenantContextOut], summary="当前租户上下文")
def current_tenant_context(
    context: TenantContextDep,
    session: DbSession,
) -> ApiResponse[TenantContextOut]:
    """需要 X-Tenant-ID。permission_codes 每次查库，角色变更后下一次请求立即生效。"""
    codes = sorted(AuthorizationService(session).permission_codes(context))
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
    "/current/my-permissions",
    response_model=ApiResponse[MyPermissionsOut],
    summary="当前成员有效权限",
)
def current_member_permissions(
    context: TenantContextDep,
    session: DbSession,
) -> ApiResponse[MyPermissionsOut]:
    """复用 TenantContext 与 AuthorizationService，不另建一套授权。

    必须声明在 /{tenant_id} 之前，否则 current 会被当成整数路径参数。
    """
    return ok(AuthorizationService(session).current_member_access(context))


@router.get("/{tenant_id}", response_model=ApiResponse[TenantOut], summary="租户详情")
def get_tenant(
    tenant_id: int,
    user: CurrentUser,
    session: DbSession,
) -> ApiResponse[TenantOut]:
    return ok(TenantService(session).get_tenant(user=user, tenant_id=tenant_id))


@router.get(
    "/{tenant_id}/members",
    response_model=ApiResponse[MemberListOut],
    summary="租户成员",
)
def list_members(
    tenant_id: int,
    context: MemberReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[MemberListOut]:
    return ok(
        TenantService(session).list_members(
            context=context,
            tenant_id=tenant_id,
            q=q,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/{tenant_id}/members",
    response_model=ApiResponse[MemberOut],
    summary="添加成员",
)
def add_member(
    tenant_id: int,
    payload: MemberCreate,
    context: MemberCreateContext,
    session: DbSession,
) -> ApiResponse[MemberOut]:
    member = TenantService(session).add_member(
        context=context,
        tenant_id=tenant_id,
        email=payload.email,
        target_user_id=payload.user_id,
        role_ids=payload.role_ids,
    )
    return ok(member, "已加入")


@router.post(
    "/{tenant_id}/members/accounts",
    response_model=ApiResponse[MemberCreatedOut],
    summary="创建成员账号",
)
def create_member_account(
    tenant_id: int,
    payload: MemberAccountCreate,
    context: MemberCreateContext,
    session: DbSession,
) -> ApiResponse[MemberCreatedOut]:
    """代建全局登录账号并加入当前企业。temporary_password 只在本响应出现一次。"""
    member = TenantService(session).create_member_account(
        context=context,
        tenant_id=tenant_id,
        display_name=payload.display_name,
        email=payload.email,
        role_ids=payload.role_ids,
    )
    return ok(member, "账号已创建")


@router.get(
    "/{tenant_id}/members/{member_id}",
    response_model=ApiResponse[MemberDetailOut],
    summary="成员详情",
)
def get_member(
    tenant_id: int,
    member_id: int,
    context: MemberReadContext,
    session: DbSession,
) -> ApiResponse[MemberDetailOut]:
    return ok(
        TenantService(session).get_member(
            context=context,
            tenant_id=tenant_id,
            member_id=member_id,
        )
    )


@router.get(
    "/{tenant_id}/members/{member_id}/permissions",
    response_model=ApiResponse[MemberDetailOut],
    summary="成员有效权限",
)
def get_member_permissions(
    tenant_id: int,
    member_id: int,
    context: MemberReadContext,
    session: DbSession,
) -> ApiResponse[MemberDetailOut]:
    return ok(
        TenantService(session).get_member(
            context=context,
            tenant_id=tenant_id,
            member_id=member_id,
        )
    )


@router.put(
    "/{tenant_id}/members/{member_id}/roles",
    response_model=ApiResponse[MemberOut],
    summary="修改成员角色",
)
def replace_member_roles(
    tenant_id: int,
    member_id: int,
    payload: MemberRolesUpdate,
    context: MemberRoleUpdateContext,
    session: DbSession,
) -> ApiResponse[MemberOut]:
    member = TenantService(session).replace_member_roles(
        context=context,
        tenant_id=tenant_id,
        member_id=member_id,
        role_ids=payload.role_ids,
    )
    return ok(member)


@router.patch(
    "/{tenant_id}/members/{member_id}",
    response_model=ApiResponse[MemberOut],
    summary="更新成员",
)
def update_member(
    tenant_id: int,
    member_id: int,
    payload: MemberUpdate,
    context: TenantContextDep,
    session: DbSession,
) -> ApiResponse[MemberOut]:
    """可改企业内 display_name 和/或状态。权限按提交字段分别校验。"""
    member = TenantService(session).update_member(
        context=context,
        tenant_id=tenant_id,
        member_id=member_id,
        status=payload.status,
        display_name=payload.display_name,
        fields=payload.model_fields_set,
    )
    return ok(member)


@router.delete(
    "/{tenant_id}/members/{member_id}",
    response_model=ApiResponse[None],
    summary="移除成员",
)
def remove_member(
    tenant_id: int,
    member_id: int,
    context: MemberRemoveContext,
    session: DbSession,
) -> ApiResponse[None]:
    TenantService(session).remove_member(
        context=context,
        tenant_id=tenant_id,
        member_id=member_id,
    )
    return ok(None, "已移出企业")
