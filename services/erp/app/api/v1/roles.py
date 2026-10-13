from fastapi import APIRouter

from app.api.deps import DbSession
from app.api.rbac_deps import (
    RoleCreateContext,
    RoleDeleteContext,
    RolePermissionUpdateContext,
    RoleReadContext,
    RoleUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.rbac import RoleCreate, RoleOut, RolePermissionUpdate, RoleUpdate
from app.services.rbac import RoleService

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=ApiResponse[list[RoleOut]], summary="当前租户角色")
def list_roles(context: RoleReadContext, session: DbSession) -> ApiResponse[list[RoleOut]]:
    return ok(RoleService(session).list_roles(context))


@router.post("", response_model=ApiResponse[RoleOut], summary="创建自定义角色")
def create_role(
    payload: RoleCreate,
    context: RoleCreateContext,
    session: DbSession,
) -> ApiResponse[RoleOut]:
    return ok(RoleService(session).create_role(context, payload), "创建成功")


@router.get("/{role_id}", response_model=ApiResponse[RoleOut], summary="角色详情")
def get_role(
    role_id: int,
    context: RoleReadContext,
    session: DbSession,
) -> ApiResponse[RoleOut]:
    return ok(RoleService(session).get_role(context, role_id))


@router.patch("/{role_id}", response_model=ApiResponse[RoleOut], summary="修改自定义角色")
def update_role(
    role_id: int,
    payload: RoleUpdate,
    context: RoleUpdateContext,
    session: DbSession,
) -> ApiResponse[RoleOut]:
    return ok(RoleService(session).update_role(context, role_id, payload))


@router.put("/{role_id}/permissions", response_model=ApiResponse[RoleOut], summary="替换角色权限")
def replace_role_permissions(
    role_id: int,
    payload: RolePermissionUpdate,
    context: RolePermissionUpdateContext,
    session: DbSession,
) -> ApiResponse[RoleOut]:
    return ok(
        RoleService(session).replace_role_permissions(
            context,
            role_id,
            payload.permission_ids,
        )
    )


@router.delete("/{role_id}", response_model=ApiResponse[None], summary="删除自定义角色")
def delete_role(
    role_id: int,
    context: RoleDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    RoleService(session).delete_role(context, role_id)
    return ok(None, "已删除")
