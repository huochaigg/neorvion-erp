"""当前请求的租户身份。X-Tenant-ID 只是意愿，必须再查 tenant_members。"""

from dataclasses import dataclass

TENANT_HEADER = "X-Tenant-ID"


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str
