"""当前请求的租户身份。X-Tenant-ID 只是意愿，必须经 ERP 身份内省确认。"""

from dataclasses import dataclass, field

TENANT_HEADER = "X-Tenant-ID"
INTERNAL_SERVICE_HEADER = "X-Internal-Service-Key"


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str
    permission_codes: frozenset[str] = field(default_factory=frozenset)
    token_jti: str = ""
