"""内部身份内省。Knowledge 等服务用用户 JWT + 服务密钥换取租户成员与权限。"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request

from app.api.deps import DbSession, TenantContextDep, _extract_bearer_token
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.schemas.common import ApiResponse, ok
from app.schemas.identity import IdentityIntrospectOut
from app.services.authorization import AuthorizationService

INTERNAL_SERVICE_HEADER = "X-Internal-Service-Key"

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_internal_service_key(request: Request) -> None:
    """校验服务间密钥。空配置视为未启用，避免误开放。"""
    expected = settings.internal_service_key
    if not expected:
        raise AppError("内部身份接口未配置", code=40330, status_code=403)
    provided = request.headers.get(INTERNAL_SERVICE_HEADER, "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise AppError("内部服务凭证无效", code=40331, status_code=403)


@router.post(
    "/identity/introspect",
    response_model=ApiResponse[IdentityIntrospectOut],
    summary="内部身份内省",
)
def introspect_identity(
    request: Request,
    context: TenantContextDep,
    session: DbSession,
) -> ApiResponse[IdentityIntrospectOut]:
    """把当前用户 JWT 和 X-Tenant-ID 换成已校验的成员身份与权限编码。

    功能：给 Knowledge 等独立服务确认「谁、哪个企业、有哪些权限」，
    避免它们直连 ERP MySQL。
    参数：Authorization Bearer、X-Tenant-ID、X-Internal-Service-Key。
    返回：user_id / tenant_id / member_id / is_owner / role / permission_codes / jti / exp。
    异常：服务密钥错误 40331；JWT 无效 401；非成员 40310/40410。
    流程：先校验服务密钥，再走与业务接口相同的 CurrentUser + TenantContext，
    最后按 AuthorizationService 汇总权限。OWNER 仍按目录动态拥有全部已知权限。
    """
    _require_internal_service_key(request)
    token = _extract_bearer_token(request)
    payload = decode_token(token, expected_type="access")
    codes = sorted(AuthorizationService(session).permission_codes(context))
    exp = payload.get("exp") or 0
    return ok(
        IdentityIntrospectOut(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            member_id=context.member_id,
            is_owner=context.is_owner,
            role=context.role,
            permission_codes=codes,
            token_jti=str(payload.get("jti") or ""),
            token_exp=int(exp),
        )
    )
