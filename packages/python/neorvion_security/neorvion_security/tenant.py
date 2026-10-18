"""请求级身份快照。X-Tenant-ID 只是客户端意愿，不能单独当作成员证明。"""

from dataclasses import dataclass, field

TENANT_HEADER = "X-Tenant-ID"
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """已通过 JWT + Redis 快照校验的身份。

    permission_codes 来自 IAM 写入的授权快照，不是 JWT 内嵌权限。
    业务资源 ACL（订单归属、文档共享）仍须各服务二次校验。
    """

    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str
    permission_codes: frozenset[str] = field(default_factory=frozenset)
    role_codes: tuple[str, ...] = ()
    token_jti: str = ""
    token_version: int = 0
    authz_version: int = 0
    is_platform_admin: bool = False
    must_change_password: bool = False
    display_name: str = ""
    email: str = ""
    api_key_id: int | None = None
    api_key_scopes: frozenset[str] = field(default_factory=frozenset)
    api_key_base_ids: frozenset[int] | None = None
    session_id: str = ""
    high_risk_verified: bool = False
    authz_source: str = "snapshot"

    def has_all(self, *codes: str) -> bool:
        """当前快照是否具备全部功能权限。"""
        return all(code in self.permission_codes for code in codes)

    def has_any(self, *codes: str) -> bool:
        """当前快照是否具备任一功能权限。"""
        return any(code in self.permission_codes for code in codes)
