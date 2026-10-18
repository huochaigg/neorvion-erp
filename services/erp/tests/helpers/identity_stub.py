"""测试用身份适配器：把原 ERP 认证/角色 API 映射为 JWT + Redis 快照。

生产应用不包含本路由。权限判定仍走真实 TenantContextDep 与 AuthorizationService。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

from app.api.deps import TenantContextDep
from app.core.iam import jwt_verifier, snapshot_store, test_signer
from app.core.permissions import (
    DEFAULT_ROLE_TEMPLATES,
    PERMISSION_CATALOG,
    PERMISSION_TREE,
    PermissionCode,
    known_permission_codes,
)
from app.schemas.common import ApiResponse, ok
from app.services.authorization import AuthorizationService
from fastapi import APIRouter, FastAPI, Query, Request
from neorvion_security import AuthzSnapshot
from neorvion_security.snapshot import authz_version_key
from pydantic import BaseModel, EmailStr, Field

_user_ids = count(1)
_tenant_ids = count(1)
_member_ids = count(1)
_role_ids = count(1)

users_by_email: dict[str, dict] = {}
users_by_id: dict[int, dict] = {}
tenants: dict[int, dict] = {}
roles: dict[int, dict] = {}
members: dict[int, dict] = {}
permission_ids: dict[str, int] = {}
permission_by_id: dict[int, str] = {}


def reset_identity_stub() -> None:
    """每个测试清空内存身份，与 Redis flush 对齐。"""
    global _user_ids, _tenant_ids, _member_ids, _role_ids
    _user_ids = count(1)
    _tenant_ids = count(1)
    _member_ids = count(1)
    _role_ids = count(1)
    users_by_email.clear()
    users_by_id.clear()
    tenants.clear()
    roles.clear()
    members.clear()
    permission_ids.clear()
    permission_by_id.clear()
    for index, item in enumerate(PERMISSION_CATALOG, start=1):
        code = str(item[0])
        permission_ids[code] = index
        permission_by_id[index] = code


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _issue_token(user_id: int) -> str:
    token, _jti = test_signer().sign(
        user_id=user_id,
        token_type="access",
        ttl=timedelta(minutes=30),
        token_version=0,
    )
    return token


def _permission_out(code: str) -> dict:
    item = next((row for row in PERMISSION_CATALOG if str(row[0]) == code), None)
    return {
        "id": permission_ids[code],
        "code": code,
        "name": item[1] if item else code,
        "module": item[2] if item else "",
        "description": item[3] if item else "",
        "deprecated": False,
    }


def _role_out(role: dict) -> dict:
    codes = sorted(role["permission_codes"])
    return {
        "id": role["id"],
        "tenant_id": role["tenant_id"],
        "name": role["name"],
        "code": role["code"],
        "description": role["description"],
        "is_system": role["is_system"],
        "created_at": role["created_at"],
        "updated_at": role["updated_at"],
        "permissions": [_permission_out(code) for code in codes if code in permission_ids],
        "member_count": sum(1 for member in members.values() if role["id"] in member["role_ids"]),
    }


def _refresh_member_snapshot(member: dict) -> None:
    tenant = tenants[member["tenant_id"]]
    user = users_by_id[member["user_id"]]
    codes: set[str] = set()
    role_codes: list[str] = []
    for role_id in member["role_ids"]:
        role = roles.get(role_id)
        if role is None:
            continue
        role_codes.append(role["code"])
        codes.update(role["permission_codes"])
    if member["is_owner"]:
        codes = set(known_permission_codes())
        if "OWNER" not in role_codes:
            role_codes.insert(0, "OWNER")
    store = snapshot_store()
    raw_aver = store.redis.get(authz_version_key(user["id"], tenant["id"]))
    authz_version = int(raw_aver) if raw_aver is not None else 1
    store.save(
        AuthzSnapshot(
            user_id=user["id"],
            tenant_id=tenant["id"],
            member_id=member["id"],
            is_owner=member["is_owner"],
            role=role_codes[0] if role_codes else "VIEWER",
            status=member["status"],
            tenant_status=tenant["status"],
            permission_codes=tuple(sorted(codes)),
            role_codes=tuple(role_codes),
            authz_version=authz_version,
            token_version=store.current_token_version(user["id"]),
            must_change_password=False,
            display_name=user["display_name"],
            email=user["email"],
        )
    )


def _seed_system_roles(tenant_id: int) -> None:
    now = _now()
    for code, name, description, perm_codes in DEFAULT_ROLE_TEMPLATES:
        role_id = next(_role_ids)
        roles[role_id] = {
            "id": role_id,
            "tenant_id": tenant_id,
            "name": name,
            "code": str(code),
            "description": description,
            "is_system": True,
            "created_at": now,
            "updated_at": now,
            "permission_codes": {str(item) for item in perm_codes},
        }


router = APIRouter()


class RegisterIn(BaseModel):
    email: EmailStr
    display_name: str = "User"
    encrypted_password: str | None = None
    key_id: str | None = None
    challenge_id: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    encrypted_password: str | None = None
    key_id: str | None = None
    challenge_id: str | None = None


class TenantIn(BaseModel):
    name: str
    code: str | None = None


class RoleIn(BaseModel):
    name: str
    code: str
    description: str | None = None
    permission_ids: list[int] = Field(default_factory=list)


class RolePatchIn(BaseModel):
    name: str | None = None
    description: str | None = None


class RolePermIn(BaseModel):
    permission_ids: list[int]


class MemberIn(BaseModel):
    email: EmailStr | None = None
    user_id: int | None = None
    role_ids: list[int] = Field(default_factory=list)


class MemberPatchIn(BaseModel):
    display_name: str | None = None
    status: str | None = None


class MemberRolesIn(BaseModel):
    role_ids: list[int]


@router.post("/api/v1/auth/register")
def register(payload: RegisterIn) -> ApiResponse[dict]:
    email = str(payload.email).strip().lower()
    if email in users_by_email:
        from app.core.exceptions import AppError

        raise AppError("邮箱已注册", code=40910, status_code=409)
    user_id = next(_user_ids)
    user = {
        "id": user_id,
        "email": email,
        "display_name": payload.display_name,
        "status": "ACTIVE",
        "created_at": _now(),
        "must_change_password": False,
    }
    users_by_email[email] = user
    users_by_id[user_id] = user
    return ok({"id": user_id, "email": email, "display_name": payload.display_name, "status": "ACTIVE", "created_at": user["created_at"], "must_change_password": False}, "注册成功")


@router.post("/api/v1/auth/login")
def login(payload: LoginIn) -> ApiResponse[dict]:
    email = str(payload.email).strip().lower()
    user = users_by_email.get(email)
    if user is None:
        from app.core.exceptions import AppError

        raise AppError("邮箱或密码错误", code=40101, status_code=401)
    token = _issue_token(user["id"])
    return ok({"access_token": token, "token_type": "bearer", "expires_in": 1800})


@router.get("/api/v1/auth/me")
def me(request: Request) -> ApiResponse[dict]:
    header = request.headers.get("Authorization") or ""
    token = header.removeprefix("Bearer ").strip()
    claims = jwt_verifier().verify_access(token)
    user = users_by_id[claims.user_id]
    return ok({**user, "last_login_at": None})


@router.post("/api/v1/tenants")
def create_tenant(payload: TenantIn, request: Request) -> ApiResponse[dict]:
    header = request.headers.get("Authorization") or ""
    token = header.removeprefix("Bearer ").strip()
    claims = jwt_verifier().verify_access(token)
    user = users_by_id[claims.user_id]
    tenant_id = next(_tenant_ids)
    code = (payload.code or f"t{tenant_id}").strip().lower()
    now = _now()
    tenants[tenant_id] = {
        "id": tenant_id,
        "name": payload.name,
        "code": code,
        "status": "ACTIVE",
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
        "my_role": "OWNER",
        "my_status": "ACTIVE",
        "is_owner": True,
    }
    _seed_system_roles(tenant_id)
    owner_role = next(role for role in roles.values() if role["tenant_id"] == tenant_id and role["code"] == "OWNER")
    member_id = next(_member_ids)
    members[member_id] = {
        "id": member_id,
        "tenant_id": tenant_id,
        "user_id": user["id"],
        "role_ids": [owner_role["id"]],
        "status": "ACTIVE",
        "is_owner": True,
        "display_name": user["display_name"],
        "email": user["email"],
    }
    _refresh_member_snapshot(members[member_id])
    return ok(tenants[tenant_id], "创建成功")


@router.get("/api/v1/tenants")
def list_tenants(request: Request) -> ApiResponse[list[dict]]:
    header = request.headers.get("Authorization") or ""
    token = header.removeprefix("Bearer ").strip()
    claims = jwt_verifier().verify_access(token)
    owned = [
        {**tenant, "my_role": "OWNER" if member["is_owner"] else "MEMBER", "my_status": member["status"], "is_owner": member["is_owner"]}
        for member in members.values()
        if member["user_id"] == claims.user_id
        for tenant in [tenants[member["tenant_id"]]]
    ]
    return ok(owned)


def _tree_nodes(nodes) -> list[dict]:
    result = []
    for node in nodes:
        code = str(node.permission_code) if node.permission_code else None
        result.append(
            {
                "key": node.key,
                "title": node.title,
                "type": node.type,
                "permission_id": permission_ids.get(code) if code else None,
                "permission_code": code,
                "children": _tree_nodes(node.children),
            }
        )
    return result


@router.get("/api/v1/permissions")
def list_permissions(context: TenantContextDep) -> ApiResponse[list[dict]]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_PERMISSION_READ,))
    return ok([_permission_out(str(item[0])) for item in PERMISSION_CATALOG])


@router.get("/api/v1/permissions/tree")
def list_permission_tree(context: TenantContextDep) -> ApiResponse[list[dict]]:
    AuthorizationService().require_any(
        context,
        (
            PermissionCode.TENANT_PERMISSION_READ,
            PermissionCode.TENANT_ROLE_READ,
            PermissionCode.TENANT_ROLE_CREATE,
            PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,
        ),
    )
    return ok(_tree_nodes(PERMISSION_TREE))


@router.get("/api/v1/roles")
def list_roles(context: TenantContextDep) -> ApiResponse[list[dict]]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_ROLE_READ,))
    return ok([_role_out(role) for role in roles.values() if role["tenant_id"] == context.tenant_id])


@router.post("/api/v1/roles")
def create_role(payload: RoleIn, context: TenantContextDep) -> ApiResponse[dict]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_ROLE_CREATE,))
    role_id = next(_role_ids)
    now = _now()
    codes = {permission_by_id[item] for item in payload.permission_ids if item in permission_by_id}
    roles[role_id] = {
        "id": role_id,
        "tenant_id": context.tenant_id,
        "name": payload.name,
        "code": payload.code,
        "description": payload.description or "",
        "is_system": False,
        "created_at": now,
        "updated_at": now,
        "permission_codes": codes,
    }
    return ok(_role_out(roles[role_id]), "创建成功")


@router.put("/api/v1/roles/{role_id}/permissions")
def replace_role_permissions(role_id: int, payload: RolePermIn, context: TenantContextDep) -> ApiResponse[dict]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,))
    role = roles[role_id]
    role["permission_codes"] = {permission_by_id[item] for item in payload.permission_ids if item in permission_by_id}
    role["updated_at"] = _now()
    for member in members.values():
        if role_id in member["role_ids"]:
            snapshot_store().bump_authz_version(member["user_id"], member["tenant_id"])
            _refresh_member_snapshot(member)
    return ok(_role_out(role))


@router.post("/api/v1/tenants/{tenant_id}/members")
def add_member(tenant_id: int, payload: MemberIn, context: TenantContextDep) -> ApiResponse[dict]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_MEMBER_CREATE,))
    email = str(payload.email).strip().lower() if payload.email else None
    user = users_by_email.get(email or "") if email else users_by_id.get(payload.user_id or 0)
    if user is None:
        from app.core.exceptions import AppError

        raise AppError("用户不存在", code=40420, status_code=404)
    role_ids = payload.role_ids or [
        role["id"]
        for role in roles.values()
        if role["tenant_id"] == tenant_id and role["code"] == "VIEWER"
    ]
    member_id = next(_member_ids)
    members[member_id] = {
        "id": member_id,
        "tenant_id": tenant_id,
        "user_id": user["id"],
        "role_ids": role_ids,
        "status": "ACTIVE",
        "is_owner": False,
        "display_name": user["display_name"],
        "email": user["email"],
    }
    _refresh_member_snapshot(members[member_id])
    return ok(_member_out(members[member_id]), "添加成功")


def _member_out(member: dict) -> dict:
    user = users_by_id[member["user_id"]]
    role_briefs = [
        {"id": roles[role_id]["id"], "code": roles[role_id]["code"], "name": roles[role_id]["name"], "is_system": roles[role_id]["is_system"]}
        for role_id in member["role_ids"]
        if role_id in roles
    ]
    return {
        "id": member["id"],
        "tenant_id": member["tenant_id"],
        "user_id": member["user_id"],
        "role": role_briefs[0]["code"] if role_briefs else "VIEWER",
        "status": member["status"],
        "display_name": member["display_name"],
        "member_display_name": member["display_name"],
        "user_display_name": user["display_name"],
        "email": user["email"],
        "is_owner": member["is_owner"],
        "roles": role_briefs,
    }


@router.get("/api/v1/tenants/{tenant_id}/members")
def list_members(
    tenant_id: int,
    context: TenantContextDep,
    q: str | None = None,
    status: str | None = None,
    page: int = Query(default=1),
    page_size: int = Query(default=20, alias="page_size"),
) -> ApiResponse[dict]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_MEMBER_READ,))
    items = [_member_out(member) for member in members.values() if member["tenant_id"] == tenant_id]
    if status:
        items = [item for item in items if item["status"] == status]
    if q:
        keyword = q.lower()
        items = [item for item in items if keyword in item["email"] or keyword in item["display_name"].lower()]
    start = (page - 1) * page_size
    return ok({"items": items[start : start + page_size], "total": len(items), "page": page, "page_size": page_size})


@router.get("/api/v1/tenants/{tenant_id}/members/{member_id}")
def get_member(tenant_id: int, member_id: int, context: TenantContextDep) -> ApiResponse[dict]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_MEMBER_READ,))
    return ok(_member_out(members[member_id]))


@router.patch("/api/v1/tenants/{tenant_id}/members/{member_id}")
def patch_member(tenant_id: int, member_id: int, payload: MemberPatchIn, context: TenantContextDep) -> ApiResponse[dict]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_MEMBER_UPDATE,))
    member = members[member_id]
    if payload.display_name:
        member["display_name"] = payload.display_name
    if payload.status:
        member["status"] = payload.status
        snapshot_store().bump_authz_version(member["user_id"], tenant_id)
    _refresh_member_snapshot(member)
    return ok(_member_out(member))


@router.put("/api/v1/tenants/{tenant_id}/members/{member_id}/roles")
def put_member_roles(tenant_id: int, member_id: int, payload: MemberRolesIn, context: TenantContextDep) -> ApiResponse[dict]:
    AuthorizationService().require_all(context, (PermissionCode.TENANT_MEMBER_ROLE_UPDATE,))
    member = members[member_id]
    member["role_ids"] = payload.role_ids
    snapshot_store().bump_authz_version(member["user_id"], tenant_id)
    _refresh_member_snapshot(member)
    return ok(_member_out(member))


def install_identity_stub(app: FastAPI) -> None:
    """把测试身份路由挂到 FastAPI 应用。"""
    reset_identity_stub()
    app.include_router(router)
