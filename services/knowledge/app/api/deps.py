"""HTTP 依赖。JWT 验签 + Redis 快照写在这里，业务 Router 不要重复实现。"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import set_tenant_context
from app.core.exceptions import AppError, from_security_error
from app.core.iam import jwt_verifier, snapshot_store
from app.core.permissions import PermissionCode
from app.core.tenant import TENANT_HEADER, TenantContext
from app.db.session import get_db
from app.repositories.ops import ApiKeyRepository
from app.services.api_keys import enforce_rate_limit, hash_api_key
from app.services.authorization import AuthorizationService
from neorvion_security import SecurityError

DbSession = Annotated[AsyncSession, Depends(get_db)]


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


async def get_tenant_context(request: Request) -> TenantContext:
    """先验签 IAM JWT，再读 Redis 快照。前端传入的 tenant_id 不能单独采信。"""
    token = _extract_bearer_token(request)
    tenant_id = _parse_tenant_id(request.headers.get(TENANT_HEADER))
    try:
        claims = jwt_verifier().verify_access(token)
        context = snapshot_store().load(claims=claims, tenant_id=tenant_id)
    except SecurityError as exc:
        raise from_security_error(exc) from exc
    set_tenant_context(tenant_id=context.tenant_id, user_id=context.user_id)
    return context


async def _resolve_api_key(request: Request, session: AsyncSession, token: str) -> TenantContext:
    """用 Key 哈希定位身份。租户以 Key 记录为准，前端 X-Tenant-Id 不能改绑其他企业。"""
    if not token.startswith("nk_") or len(token) < 20:
        raise AppError("无效的 API Key", code=40103, status_code=401)
    repo = ApiKeyRepository(session)
    row = await repo.get_by_hash(hash_api_key(token))
    if row is None or row.revoked_at is not None:
        raise AppError("API Key 无效或已撤销", code=40103, status_code=401)
    if row.expires_at is not None and row.expires_at <= datetime.now(UTC):
        raise AppError("API Key 已过期", code=40104, status_code=401)
    header_tenant = request.headers.get(TENANT_HEADER)
    if header_tenant and header_tenant.strip():
        wanted = _parse_tenant_id(header_tenant)
        if wanted != row.tenant_id:
            raise AppError("API Key 不能访问其他租户", code=40365, status_code=403)
    enforce_rate_limit(row.id)
    await repo.touch_used(row.id)
    await session.commit()
    bound = [int(item) for item in (row.knowledge_base_ids or [])]
    context = TenantContext(
        user_id=row.created_by,
        tenant_id=row.tenant_id,
        member_id=0,
        is_owner=False,
        role="API_KEY",
        permission_codes=frozenset({PermissionCode.KNOWLEDGE_READ.value}),
        token_jti=f"apikey:{row.id}",
        api_key_id=row.id,
        api_key_scopes=frozenset(str(item) for item in (row.scopes or [])),
        api_key_base_ids=frozenset(bound) if bound else None,
    )
    set_tenant_context(tenant_id=context.tenant_id, user_id=context.user_id)
    return context


async def get_read_context(request: Request, session: DbSession) -> TenantContext:
    header = request.headers.get("Authorization") or ""
    token = ""
    if header.startswith("Bearer "):
        token = header.removeprefix("Bearer ").strip()
    elif header.startswith("ApiKey "):
        token = header.removeprefix("ApiKey ").strip()
    if token.startswith("nk_"):
        return await _resolve_api_key(request, session, token)
    context = await get_tenant_context(request)
    AuthorizationService().require_all(context, (PermissionCode.KNOWLEDGE_READ,))
    return context


def require_api_scope(scope: str):
    def dependency(context: KnowledgeReadContext) -> TenantContext:
        if context.api_key_id is not None and scope not in context.api_key_scopes:
            raise AppError("API Key 无权调用该接口", code=40364, status_code=403)
        return context

    return dependency


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
KnowledgeReadContext = Annotated[TenantContext, Depends(get_read_context)]


def require_permission(*codes: str):
    def dependency(context: TenantContextDep) -> TenantContext:
        AuthorizationService().require_all(context, codes)
        return context

    return dependency


KnowledgeCreateContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.KNOWLEDGE_CREATE)),
]
KnowledgeUpdateContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.KNOWLEDGE_UPDATE)),
]
KnowledgeDeleteContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.KNOWLEDGE_DELETE)),
]
