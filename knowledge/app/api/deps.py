"""HTTP 依赖。JWT 验签 + ERP 身份内省写在这里，业务 Router 不要重复实现。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import set_tenant_context
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.security import decode_access_token
from app.core.tenant import TENANT_HEADER, TenantContext
from app.db.session import get_db
from app.services.authorization import AuthorizationService
from app.services.identity import ErpIdentityClient, identity_client

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_identity_client() -> ErpIdentityClient:
    return identity_client


IdentityClientDep = Annotated[ErpIdentityClient, Depends(get_identity_client)]


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


async def get_tenant_context(
    request: Request,
    client: IdentityClientDep,
) -> TenantContext:
    """先验签 JWT，再向 ERP 确认租户成员与权限。前端传入的 tenant_id 不能单独采信。"""
    token = _extract_bearer_token(request)
    payload = decode_access_token(token)
    tenant_id = _parse_tenant_id(request.headers.get(TENANT_HEADER))
    user_id = int(payload["sub"])
    context = await client.resolve(
        access_token=token,
        tenant_id=tenant_id,
        jti=str(payload["jti"]),
    )
    if context.user_id != user_id:
        raise AppError("无效的登录凭证", code=40102, status_code=401)
    set_tenant_context(tenant_id=context.tenant_id, user_id=context.user_id)
    return context


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]


def require_permission(*codes: str):
    def dependency(context: TenantContextDep) -> TenantContext:
        AuthorizationService().require_all(context, codes)
        return context

    return dependency


KnowledgeReadContext = Annotated[
    TenantContext,
    Depends(require_permission(PermissionCode.KNOWLEDGE_READ)),
]
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
