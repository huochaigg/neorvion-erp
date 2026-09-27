"""权限判定。HTTP Depends 和 Service / 后续 Agent、Celery 都走这里，避免只挡 Router。"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import known_permission_codes
from app.core.tenant import TenantContext
from app.models.tenant import MemberRole, MemberStatus, TenantStatus
from app.repositories.rbac import RoleRepository
from app.repositories.tenant import TenantMemberRepository


class AuthorizationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.roles = RoleRepository(session)
        self.members = TenantMemberRepository(session)

    def permission_codes(self, context: TenantContext) -> set[str]:
        # OWNER 列表示所有权，不是「跳过校验」的后门：未知权限编码仍然会在 require_* 里报配置错误。
        # 目录里已经登记的权限，所有者全部拥有，避免每次加新 code 都漏给历史 OWNER。
        if context.is_owner:
            return set(known_permission_codes())
        return self.roles.list_permission_codes_for_member(
            tenant_id=context.tenant_id,
            member_id=context.member_id,
        )

    def require_all(self, context: TenantContext, codes: Sequence[str]) -> None:
        owned = self.permission_codes(context)
        self._assert_known(codes)
        missing = [code for code in codes if code not in owned]
        if missing:
            raise AppError("缺少权限", code=40320, status_code=403)

    def require_any(self, context: TenantContext, codes: Sequence[str]) -> None:
        owned = self.permission_codes(context)
        self._assert_known(codes)
        if not any(code in owned for code in codes):
            raise AppError("缺少权限", code=40320, status_code=403)

    def require_all_for_user(
        self,
        *,
        user_id: int,
        tenant_id: int,
        codes: Sequence[str],
    ) -> TenantContext:
        """给 Celery / Agent / 内部调用复用。先还原成员身份，再做与 HTTP 相同的权限判断。"""
        context = self.build_context(user_id=user_id, tenant_id=tenant_id)
        self.require_all(context, codes)
        return context

    def build_context(self, *, user_id: int, tenant_id: int) -> TenantContext:
        member = self.members.get_by_tenant_user(tenant_id, user_id)
        if member is None or member.tenant is None:
            raise AppError("租户不存在或不可访问", code=40410, status_code=404)
        if member.status != MemberStatus.ACTIVE.value:
            raise AppError("无权访问该租户", code=40310, status_code=403)
        if member.tenant.status != TenantStatus.ACTIVE.value:
            raise AppError("无权访问该租户", code=40310, status_code=403)
        return TenantContext(
            user_id=user_id,
            tenant_id=tenant_id,
            member_id=member.id,
            is_owner=member.role == MemberRole.OWNER.value,
            role=member.role,
        )

    @staticmethod
    def _assert_known(codes: Sequence[str]) -> None:
        catalog = known_permission_codes()
        for code in codes:
            if code not in catalog:
                raise AppError("权限编码未定义", code=50021, status_code=500)
