"""当前请求的租户身份。X-Tenant-ID 只是意愿，必须经 IAM 快照确认。"""

from neorvion_security.tenant import TENANT_HEADER, TenantContext

INTERNAL_SERVICE_HEADER = "X-Internal-Service-Key"

__all__ = ["INTERNAL_SERVICE_HEADER", "TENANT_HEADER", "TenantContext"]
