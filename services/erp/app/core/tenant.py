"""当前请求的租户身份。X-Tenant-ID 只是意愿，必须再校验 IAM 快照。"""

from neorvion_security.tenant import TENANT_HEADER, TenantContext

__all__ = ["TENANT_HEADER", "TenantContext"]
