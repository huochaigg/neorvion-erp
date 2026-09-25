"""HTTP 依赖。JWT 解析只写在这里，业务 Router 不要重复实现。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.context import set_tenant_context
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.core.tenant import TENANT_HEADER, TenantContext
from app.db.session import get_db
from app.models.tenant import MemberRole, MemberStatus, TenantStatus
from app.models.user import User, UserStatus
from app.repositories.tenant import TenantMemberRepository
from app.repositories.user import UserRepository

DbSession = Annotated[Session, Depends(get_db)]


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise AppError("未登录", code=40100, status_code=401)
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise AppError("未登录", code=40100, status_code=401)
    return token


def get_current_user(request: Request, session: DbSession) -> User:
    """解析 Access Token 并加载当前用户。仅供受保护接口通过 CurrentUser 注入。

    公开接口见 app.core.auth_public.PUBLIC_ROUTES，尤其是 POST /api/v1/auth/refresh
    不得依赖本函数：Refresh 只校验 Cookie 中的 Refresh Token。
    """
    token = _extract_bearer_token(request)
    payload = decode_token(token, expected_type="access")
    user_id = int(payload["sub"])
    user = UserRepository(session).get_by_id(user_id)
    if user is None:
        raise AppError("未登录", code=40100, status_code=401)
    if user.status != UserStatus.ACTIVE.value:
        raise AppError("账号已被禁用", code=40300, status_code=403)
    set_tenant_context(tenant_id=None, user_id=user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _parse_tenant_id(raw: str | None) -> int:
    if raw is None or not raw.strip():
        raise AppError("缺少租户上下文", code=40030, status_code=400)
    try:
        tenant_id = int(raw.strip())
    except ValueError as exc:
        raise AppError("租户上下文无效", code=40030, status_code=400) from exc
    if tenant_id <= 0:
        raise AppError("租户上下文无效", code=40030, status_code=400)
    return tenant_id


def get_tenant_context(request: Request, user: CurrentUser, session: DbSession) -> TenantContext:
    """读取 X-Tenant-ID 后查库校验。请求头不能当作已授权身份。

    FastAPI 会先解析 CurrentUser，再执行本函数，所以业务接口只要声明
    TenantContextDep 就能同时拿到登录用户和已验证的租户。
    """
    tenant_id = _parse_tenant_id(request.headers.get(TENANT_HEADER))
    member = TenantMemberRepository(session).get_by_tenant_user(tenant_id, user.id)
    if member is None or member.tenant is None:
        raise AppError("租户不存在或不可访问", code=40410, status_code=404)
    if member.status != MemberStatus.ACTIVE.value:
        raise AppError("无权访问该租户", code=40310, status_code=403)
    if member.tenant.status != TenantStatus.ACTIVE.value:
        raise AppError("无权访问该租户", code=40310, status_code=403)
    set_tenant_context(tenant_id=tenant_id, user_id=user.id)
    return TenantContext(
        user_id=user.id,
        tenant_id=tenant_id,
        member_id=member.id,
        is_owner=member.role == MemberRole.OWNER.value,
        role=member.role,
    )


def get_current_tenant(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> TenantContext:
    """给后续业务接口复用的别名。"""
    return context


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
CurrentTenant = Annotated[TenantContext, Depends(get_current_tenant)]
