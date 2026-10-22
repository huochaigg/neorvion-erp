"""业务服务高风险回源。必须带内部密钥，读取 IAM 数据库而不是 Redis 快照。"""

from fastapi import APIRouter, Header, Request

from app.api.deps import BootstrapDb
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import decode_token
from app.models.tenant import MemberRole, MemberStatus, TenantStatus
from app.repositories.tenant import TenantMemberRepository
from app.repositories.user import UserRepository
from app.schemas.common import ApiResponse, ok
from app.schemas.session import AuthorityCheckIn, AuthorityCheckOut
from app.services.authorization import AuthorizationService
from app.services.authz_revision import current_revision
from app.services.session import SessionService
from app.services.snapshots import SnapshotService

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/authorize", response_model=ApiResponse[AuthorityCheckOut], summary="高风险权威授权")
def authorize(
    payload: AuthorityCheckIn,
    request: Request,
    session: BootstrapDb,
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> ApiResponse[AuthorityCheckOut]:
    """以 IAM 数据库为权威来源校验成员权限。Redis 仅用于加速，故障时仍以库为准。"""
    expected = settings.internal_service_key
    if not expected or not x_internal_key or x_internal_key != expected:
        raise AppError("内部授权密钥无效", code=40331, status_code=403)
    header = request.headers.get("Authorization") or ""
    if not header.startswith("Bearer "):
        raise AppError("未登录", code=40100, status_code=401)
    token = header.removeprefix("Bearer ").strip()
    claims = decode_token(token, expected_type="access")
    SnapshotService(session).drain_outbox()
    if claims.session_id:
        SessionService(session).require_active(user_id=claims.user_id, public_id=claims.session_id)
    user = UserRepository(session).get_by_id(claims.user_id)
    if user is None or user.status != "ACTIVE":
        raise AppError("账号已被禁用", code=40300, status_code=403)
    if not x_tenant_id or not x_tenant_id.strip():
        raise AppError("缺少租户上下文", code=40030, status_code=400)
    try:
        tenant_id = int(x_tenant_id.strip())
    except ValueError as exc:
        raise AppError("租户上下文无效", code=40030, status_code=400) from exc
    member = TenantMemberRepository(session).get_by_tenant_user(tenant_id, user.id)
    if member is None or member.tenant is None:
        raise AppError("租户不存在或不可访问", code=40410, status_code=404)
    if member.status != MemberStatus.ACTIVE.value or member.tenant.status != TenantStatus.ACTIVE.value:
        raise AppError("无权访问该租户", code=40310, status_code=403)
    from neorvion_security.tenant import TenantContext

    context = TenantContext(
        user_id=user.id,
        tenant_id=tenant_id,
        member_id=member.id,
        is_owner=member.role == MemberRole.OWNER.value,
        role=member.role,
        is_platform_admin=bool(user.is_platform_admin),
        high_risk_verified=True,
        authz_source="iam-db",
        session_id=claims.session_id,
    )
    authz = AuthorizationService(session)
    codes = sorted(authz.permission_codes(context))
    context = TenantContext(
        user_id=user.id,
        tenant_id=tenant_id,
        member_id=member.id,
        is_owner=member.role == MemberRole.OWNER.value,
        role=member.role,
        permission_codes=frozenset(codes),
        role_codes=tuple(authz.current_member_access(context).roles),
        token_jti=claims.jti,
        token_version=claims.token_version,
        authz_version=current_revision(session, user_id=user.id, tenant_id=tenant_id),
        is_platform_admin=bool(user.is_platform_admin),
        must_change_password=bool(user.must_change_password),
        display_name=member.display_name or user.display_name,
        email=user.email,
        session_id=claims.session_id,
        high_risk_verified=True,
        authz_source="iam-db",
    )
    if payload.codes:
        authz.require_all(context, payload.codes)
    return ok(
        AuthorityCheckOut(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            member_id=context.member_id,
            is_owner=context.is_owner,
            role=context.role,
            permission_codes=sorted(context.permission_codes),
            role_codes=list(context.role_codes),
            token_jti=context.token_jti,
            token_version=context.token_version,
            authz_version=context.authz_version,
            is_platform_admin=context.is_platform_admin,
            must_change_password=context.must_change_password,
            display_name=context.display_name,
            email=context.email,
            session_id=context.session_id,
        )
    )
