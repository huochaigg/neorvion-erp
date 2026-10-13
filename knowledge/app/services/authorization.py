from collections.abc import Sequence

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext

_KNOWN = frozenset(item.value for item in PermissionCode)


class AuthorizationService:
    def require_all(self, context: TenantContext, codes: Sequence[str]) -> None:
        """当前成员必须具备传入的全部 Knowledge 权限，少一个就 403。"""
        self._assert_known(codes)
        missing = [code for code in codes if code not in context.permission_codes]
        if missing:
            raise AppError("缺少权限", code=40320, status_code=403)

    @staticmethod
    def _assert_known(codes: Sequence[str]) -> None:
        for code in codes:
            if code not in _KNOWN:
                raise AppError("权限编码未定义", code=50021, status_code=500)
