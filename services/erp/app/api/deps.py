"""HTTP 依赖。JWT 解析与快照校验只写在这里，业务 Router 不要重复实现。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.context import set_tenant_context
from app.core.exceptions import AppError, from_security_error
from app.core.iam import jwt_verifier, snapshot_store
from app.core.identity_projection import project_display_user
from app.core.tenant import TENANT_HEADER, TenantContext
from app.db.session import get_db
from app.models.user import User
from neorvion_security import SecurityError

DbSession = Annotated[Session, Depends(get_db)]

_PASSWORD_CHANGE_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/auth/change-password"),
    }
)


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise AppError("未登录", code=40100, status_code=401)
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise AppError("未登录", code=40100, status_code=401)
    return token


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


def get_tenant_context(request: Request, db: DbSession) -> TenantContext:
    """校验 IAM JWT，再用 Redis 快照确认成员资格。请求头不能当作已授权身份。

    业务服务不访问 IAM HTTP。快照缺失、版本不一致或 Redis 故障时拒绝，不得放行。
    """
    token = _extract_bearer_token(request)
    try:
        claims = jwt_verifier().verify_access(token)
        tenant_id = _parse_tenant_id(request.headers.get(TENANT_HEADER))
        context = snapshot_store().load(claims=claims, tenant_id=tenant_id)
    except SecurityError as exc:
        raise from_security_error(exc) from exc
    if context.must_change_password:
        method = request.method.upper()
        path = request.url.path.rstrip("/") or "/"
        if (method, path) not in _PASSWORD_CHANGE_ALLOWED:
            raise AppError("请先修改临时密码", code=40350, status_code=403)
    project_display_user(db, context)
    set_tenant_context(tenant_id=context.tenant_id, user_id=context.user_id)
    return context


def get_current_tenant(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> TenantContext:
    """给后续业务接口复用的别名。"""
    return context


def get_current_user(request: Request, db: DbSession) -> User:
    """只校验 Access Token，不要求 X-Tenant-ID。供注册后的 /auth/me 与创建企业使用。"""
    token = _extract_bearer_token(request)
    try:
        claims = jwt_verifier().verify_access(token)
    except SecurityError as exc:
        raise from_security_error(exc) from exc
    user = db.get(User, claims.user_id)
    if user is None:
        raise AppError("用户不存在", code=40102, status_code=401)
    return user


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
CurrentTenant = Annotated[TenantContext, Depends(get_current_tenant)]
CurrentUser = Annotated[User, Depends(get_current_user)]
