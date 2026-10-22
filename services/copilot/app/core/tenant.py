"""当前请求的租户身份。X-Tenant-ID 只在 IAM 授权快照校验后生效。"""

from neorvion_security.tenant import TENANT_HEADER, TenantContext

__all__ = ["TENANT_HEADER", "TenantContext"]

