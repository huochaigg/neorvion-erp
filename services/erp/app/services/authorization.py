"""权限判定。HTTP Depends 和 Service / Worker 都走这里，避免只挡 Router。"""

from collections.abc import Sequence

from neorvion_security import SecurityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, from_security_error
from app.core.iam import snapshot_store
from app.core.permissions import (
    HIGH_RISK_PERMISSION_CODES,
    LEGACY_MANAGE_EXPANSION,
    known_permission_codes,
)
from app.core.tenant import TenantContext
from app.schemas.tenant import MyPermissionsOut


class AuthorizationService:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def permission_codes(self, context: TenantContext) -> set[str]:
        """功能权限来自 IAM 快照。OWNER 且快照未带目录时回退为全部已知编码。"""
        owned = set(context.permission_codes)
        if not owned and context.is_owner:
            owned = set(known_permission_codes())
        for legacy, extras in LEGACY_MANAGE_EXPANSION.items():
            if legacy in owned:
                owned.update(extras)
        return owned

    def current_member_access(self, context: TenantContext) -> MyPermissionsOut:
        """当前租户成员的角色编码与权限编码快照，供前端生成菜单。"""
        role_codes = list(context.role_codes)
        if context.is_owner and "OWNER" not in role_codes:
            role_codes = ["OWNER", *role_codes]
        return MyPermissionsOut(roles=sorted(set(role_codes)), permissions=sorted(self.permission_codes(context)))

    def require_all(self, context: TenantContext, codes: Sequence[str]) -> None:
        """当前成员必须具备传入的全部权限，少一个就 403。"""
        self._assert_known(codes)
        if any(code in HIGH_RISK_PERMISSION_CODES for code in codes) and not context.high_risk_verified:
            raise AppError("高风险操作未通过权威授权", code=50314, status_code=503)
        owned = self.permission_codes(context)
        missing = [code for code in codes if code not in owned]
        if missing:
            raise AppError("缺少权限", code=40320, status_code=403)

    def require_any(self, context: TenantContext, codes: Sequence[str]) -> None:
        """当前成员必须至少具备传入的其中一个权限，一个都没有就 403。"""
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
        """给 Worker / 内部调用复用。先还原快照，再做与 HTTP 相同的权限判断。"""
        context = self.build_context(user_id=user_id, tenant_id=tenant_id)
        self.require_all(context, codes)
        return context

    def build_context(self, *, user_id: int, tenant_id: int) -> TenantContext:
        """按 user_id + tenant_id 读取 IAM 快照。缺失时拒绝。"""
        try:
            return snapshot_store().load_for_principal(user_id=user_id, tenant_id=tenant_id)
        except SecurityError as exc:
            raise from_security_error(exc) from exc

    @staticmethod
    def _assert_known(codes: Sequence[str]) -> None:
        catalog = known_permission_codes()
        for code in codes:
            if code not in catalog:
                raise AppError("权限编码未定义", code=50021, status_code=500)
