"""权限判定。HTTP Depends 和 Service / 后续 Agent、Celery 都走这里，避免只挡 Router。"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import LEGACY_MANAGE_EXPANSION, SystemRoleCode, known_permission_codes
from app.core.tenant import TenantContext
from app.models.tenant import MemberRole, MemberStatus, TenantStatus
from app.repositories.rbac import RoleRepository
from app.repositories.tenant import TenantMemberRepository
from app.schemas.tenant import MyPermissionsOut


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
        owned = set(
            self.roles.list_permission_codes_for_member(
                tenant_id=context.tenant_id,
                member_id=context.member_id,
            )
        )
        # 历史角色可能只有 tenant:*:manage。接口已改成细粒度校验，
        # 这里把旧 manage 视作拥有对应细粒度，避免升级窗口内突然 403。
        for legacy, extras in LEGACY_MANAGE_EXPANSION.items():
            if legacy in owned:
                owned.update(extras)
        return owned

    def current_member_access(self, context: TenantContext) -> MyPermissionsOut:
        """当前租户成员的角色编码与权限编码快照。

        功能：给前端生成菜单和按钮；真正的接口授权仍走 require_permission。
        参数：已通过 TenantContextDep 校验的当前租户成员，不读请求体里的 user_id。
        返回：去重排序后的 roles、permissions。
        异常：成员无效时由 TenantContextDep 先抛 404/40310，这里不再重复。
        流程：按 tenant_id + member_id 读 member_roles，再并集权限。
        同一用户在 A、B 两家企业必须分别查询，Query Key 也必须带 tenant_id。
        """
        grants = self.roles.list_grants_for_member(
            tenant_id=context.tenant_id,
            member_id=context.member_id,
        )
        role_codes = sorted(
            {grant.role.code for grant in grants if grant.role is not None},
        )
        if context.is_owner and SystemRoleCode.OWNER not in role_codes:
            role_codes = [SystemRoleCode.OWNER, *role_codes]
        permissions = sorted(self.permission_codes(context))
        return MyPermissionsOut(roles=role_codes, permissions=permissions)

    def require_all(self, context: TenantContext, codes: Sequence[str]) -> None:
        """当前成员必须具备传入的全部权限，少一个就 403"""
        owned = self.permission_codes(context)
        self._assert_known(codes)
        missing = [code for code in codes if code not in owned]
        if missing:
            raise AppError("缺少权限", code=40320, status_code=403)

    def require_any(self, context: TenantContext, codes: Sequence[str]) -> None:
        """当前成员必须至少具备传入的其中一个权限，一个都没有就 403"""
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
