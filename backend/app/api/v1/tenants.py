from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, TenantContextDep
from app.schemas.common import ApiResponse, ok
from app.schemas.tenant import (
    MemberCreate,
    MemberOut,
    MemberUpdate,
    TenantContextOut,
    TenantCreate,
    TenantOut,
)
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
def current_tenant_context(context: TenantContextDep) -> ApiResponse[TenantContextOut]:
    """需要 X-Tenant-ID，并校验成员关系。后续 ERP 业务接口同样注入该依赖。"""
    return ok(
        TenantContextOut(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            member_id=context.member_id,
            is_owner=context.is_owner,
            role=context.role,
        )
    )


@router.get("/{tenant_id}", response_model=ApiResponse[TenantOut], summary="租户详情")
def get_tenant(
    tenant_id: int,
    user: CurrentUser,
    session: DbSession,
) -> ApiResponse[TenantOut]:
    return ok(TenantService(session).get_tenant(user=user, tenant_id=tenant_id))


@router.get(
    "/{tenant_id}/members",
    response_model=ApiResponse[list[MemberOut]],
    summary="租户成员",
)
def list_members(
    tenant_id: int,
    user: CurrentUser,
    session: DbSession,
) -> ApiResponse[list[MemberOut]]:
    return ok(TenantService(session).list_members(user=user, tenant_id=tenant_id))


@router.post(
    "/{tenant_id}/members",
    response_model=ApiResponse[MemberOut],
    summary="添加成员",
)
def add_member(
    tenant_id: int,
    payload: MemberCreate,
    user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MemberOut]:
    member = TenantService(session).add_member(
        user=user,
        tenant_id=tenant_id,
        target_user_id=payload.user_id,
    )
    return ok(member, "已加入")


@router.patch(
    "/{tenant_id}/members/{member_id}",
    response_model=ApiResponse[MemberOut],
    summary="更新成员状态",
)
def update_member(
    tenant_id: int,
    member_id: int,
    payload: MemberUpdate,
    user: CurrentUser,
    session: DbSession,
) -> ApiResponse[MemberOut]:
    member = TenantService(session).update_member(
        user=user,
        tenant_id=tenant_id,
        member_id=member_id,
        status=payload.status,
    )
    return ok(member)
