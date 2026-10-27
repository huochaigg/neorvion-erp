"""HTTP 依赖。JWT 解析只写在这里，业务 Router 不要重复实现。"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from neorvion_security.snapshot import token_version_key
from sqlalchemy.orm import Session

from app.core.auth_public import normalize_path
from app.core.context import set_tenant_context
from app.core.exceptions import AppError
from app.core.redis import redis_client
from app.core.security import decode_token
from app.core.tenant import TENANT_HEADER, TenantContext
from app.db.session import get_db, open_identity_session, open_tenant_session
from app.models.tenant import MemberRole, MemberStatus, TenantStatus
from app.models.user import User, UserStatus
from app.repositories.tenant import TenantMemberRepository
from app.repositories.user import UserRepository

BootstrapDb = Annotated[Session, Depends(get_db)]


def get_identity_db() -> Generator[Session, None, None]:
    """全局身份会话。不依赖租户上下文，避免和租户会话循环依赖。"""
    session = open_identity_session()
    try:
        yield session
    finally:
        session.close()


IdentityDb = Annotated[Session, Depends(get_identity_db)]

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


def get_current_user(request: Request, session: IdentityDb) -> User:
    """解析 Access Token 并加载当前用户。Refresh 不得依赖本函数。"""
    token = _extract_bearer_token(request)
    claims = decode_token(token, expected_type="access")
    if claims.subject_type != "USER":
        raise AppError("服务身份不能调用用户接口", code=40374, status_code=403)
    request.state.session_id = claims.session_id
    if claims.session_id:
        from app.services.session import SessionService

        SessionService(session).require_active(user_id=claims.user_id, public_id=claims.session_id)
    try:
        stored = redis_client.get(token_version_key(claims.user_id))
        expected = int(stored) if stored is not None else 0
        if claims.token_version != expected:
            raise AppError("登录已失效，请重新登录", code=40104, status_code=401)
    except AppError:
        raise
    except Exception:
        raise AppError("授权状态暂时不可用", code=50313, status_code=503) from None
    user = UserRepository(session).get_by_id(claims.user_id)
    if user is None:
        raise AppError("未登录", code=40100, status_code=401)
    if user.status != UserStatus.ACTIVE.value:
        raise AppError("账号已被禁用", code=40300, status_code=403)
    if user.must_change_password:
        method = request.method.upper()
        path = normalize_path(request.url.path)
        if (method, path) not in _PASSWORD_CHANGE_ALLOWED:
            raise AppError("请先修改临时密码", code=40350, status_code=403)
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


def get_tenant_context(request: Request, user: CurrentUser) -> TenantContext:
    """读取 X-Tenant-ID 后用该租户自己的会话查成员。请求头不能当作已授权身份。

    探测会话在返回前关闭，业务路由拿到的是另一个绑定同一 tenant_id 的 TenantSession。
    Outbox 只补刷当前租户；其他企业的积压等到该企业下次请求或内部授权再处理。
    """
    tenant_id = _parse_tenant_id(request.headers.get(TENANT_HEADER))
    probe = open_tenant_session(tenant_id)
    try:
        member = TenantMemberRepository(probe).get_by_tenant_user(tenant_id, user.id)
        if member is None or member.tenant is None:
            raise AppError("租户不存在或不可访问", code=40410, status_code=404)
        if member.status != MemberStatus.ACTIVE.value:
            raise AppError("无权访问该租户", code=40310, status_code=403)
        if member.tenant.status != TenantStatus.ACTIVE.value:
            raise AppError("无权访问该租户", code=40310, status_code=403)
        set_tenant_context(tenant_id=tenant_id, user_id=user.id)
        from app.services.authorization import AuthorizationService

        codes = AuthorizationService(probe).permission_codes(
            TenantContext(
                user_id=user.id,
                tenant_id=tenant_id,
                member_id=member.id,
                is_owner=member.role == MemberRole.OWNER.value,
                role=member.role,
            )
        )
        session_id = str(getattr(request.state, "session_id", "") or "")
        is_owner = member.role == MemberRole.OWNER.value
        role = member.role
        member_id = member.id
        from app.services.snapshots import SnapshotService

        SnapshotService(probe).drain_outbox()
    finally:
        probe.close()
    return TenantContext(
        user_id=user.id,
        tenant_id=tenant_id,
        member_id=member_id,
        is_owner=is_owner,
        role=role,
        permission_codes=frozenset(codes),
        is_platform_admin=bool(user.is_platform_admin),
        must_change_password=bool(user.must_change_password),
        session_id=session_id,
        high_risk_verified=True,
        authz_source="iam-db",
    )


def get_tenant_db(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> Generator[Session, None, None]:
    """租户业务会话。tenant_id 来自已经查库确认的成员关系。"""
    session = open_tenant_session(context.tenant_id)
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_tenant_db)]


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
CurrentTenant = TenantContextDep


def require_platform_admin(user: CurrentUser) -> User:
    if not user.is_platform_admin:
        raise AppError("需要平台管理员权限", code=40340, status_code=403)
    return user


PlatformAdmin = Annotated[User, Depends(require_platform_admin)]
