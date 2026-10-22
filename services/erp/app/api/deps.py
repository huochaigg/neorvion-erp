"""HTTP 依赖。JWT 解析与快照校验只写在这里，业务 Router 不要重复实现。"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from neorvion_security import SecurityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.context import set_tenant_context
from app.core.exceptions import AppError, from_security_error
from app.core.iam import authority_client, jwt_verifier, snapshot_store
from app.core.identity_projection import project_display_user
from app.core.tenant import TENANT_HEADER, TenantContext
from app.db.session import open_identity_session, open_tenant_session


def get_identity_db() -> Generator[Session, None, None]:
    """展示名投影。不依赖租户上下文，所以不会和 get_tenant_db 形成循环。"""
    session = open_identity_session()
    try:
        yield session
    finally:
        session.close()


IdentityDb = Annotated[Session, Depends(get_identity_db)]


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


def get_tenant_context(request: Request, db: IdentityDb) -> TenantContext:
    """校验 IAM JWT，再用 Redis 快照确认成员资格。请求头不能当作已授权身份。

    普通请求不访问 IAM HTTP。快照缺失、版本不一致或 Redis 故障时拒绝，不得放行。
    """
    token = _extract_bearer_token(request)
    request.state.access_token = token
    try:
        claims = jwt_verifier().verify_access(token)
        tenant_id = _parse_tenant_id(request.headers.get(TENANT_HEADER))
        context = snapshot_store().load(claims=claims, tenant_id=tenant_id)
    except SecurityError as exc:
        raise from_security_error(exc) from exc
    if context.must_change_password:
        raise AppError("请先修改临时密码", code=40350, status_code=403)
    project_display_user(db, context)
    db.commit()
    set_tenant_context(tenant_id=context.tenant_id, user_id=context.user_id)
    return context


def get_tenant_db(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> Generator[Session, None, None]:
    """业务 ORM 会话。tenant_id 只来自上面已经校验过的 TenantContext。"""
    session = open_tenant_session(context.tenant_id)
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_tenant_db)]


def get_current_tenant(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> TenantContext:
    """给后续业务接口复用的别名。"""
    return context


def get_high_risk_context(request: Request, db: IdentityDb) -> TenantContext:
    """删除、退款、权限变更等敏感操作必须回源 IAM 数据库。失败时拒绝。"""
    token = _extract_bearer_token(request)
    request.state.access_token = token
    tenant_id = _parse_tenant_id(request.headers.get(TENANT_HEADER))
    try:
        claims = jwt_verifier().verify_access(token)
        if settings.iam_authorize_url.strip() and settings.iam_internal_key.strip():
            context = snapshot_store().load(
                claims=claims,
                tenant_id=tenant_id,
                high_risk=True,
                authority=lambda: authority_client().authorize(
                    access_token=token,
                    tenant_id=tenant_id,
                ),
            )
        elif settings.is_production:
            raise AppError("高风险操作缺少权威授权通道", code=50314, status_code=503)
        else:
            from dataclasses import replace

            context = replace(
                snapshot_store().load(claims=claims, tenant_id=tenant_id),
                high_risk_verified=True,
                authz_source="snapshot-dev",
            )
    except SecurityError as exc:
        raise from_security_error(exc) from exc
    if context.must_change_password:
        raise AppError("请先修改临时密码", code=40350, status_code=403)
    project_display_user(db, context)
    db.commit()
    set_tenant_context(tenant_id=context.tenant_id, user_id=context.user_id)
    return context


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
HighRiskTenantContextDep = Annotated[TenantContext, Depends(get_high_risk_context)]
CurrentTenant = Annotated[TenantContext, Depends(get_current_tenant)]
