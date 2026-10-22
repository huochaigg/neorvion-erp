"""多租户数据库基础设施。不包含身份认证。"""

from neorvion_db.async_support import (
    GlobalIdentityAsyncSession,
    PrivilegedAsyncSession,
    TenantAsyncSession,
    open_privileged_async_session,
)
from neorvion_db.errors import (
    IsolationError,
    PrivilegeError,
    RegistryError,
    TenantContextRequired,
    TenantIsolationError,
    TenantRebindError,
)
from neorvion_db.privileges import (
    PRIVILEGED_OPERATION_KEY,
    REVIEWED_SQL_KEY,
    GlobalIdentityPurpose,
    PrivilegedOperation,
    PrivilegeGrant,
    ReviewedSql,
    privileged_option,
    reviewed_sql_option,
)
from neorvion_db.registry import (
    IsolationClass,
    IsolationRegistry,
    ModelRegistration,
    build_registry,
    infer_isolation,
)
from neorvion_db.sessions import (
    GlobalIdentitySession,
    PrivilegedSystemSession,
    TenantSession,
    open_privileged_session,
    require_tenant_id,
)
from neorvion_db.static_check import AllowedQuery, ScanReport, scan_repositories

__all__ = [
    "PRIVILEGED_OPERATION_KEY",
    "REVIEWED_SQL_KEY",
    "AllowedQuery",
    "GlobalIdentityAsyncSession",
    "GlobalIdentityPurpose",
    "GlobalIdentitySession",
    "IsolationClass",
    "IsolationError",
    "IsolationRegistry",
    "ModelRegistration",
    "PrivilegeError",
    "PrivilegeGrant",
    "PrivilegedAsyncSession",
    "PrivilegedOperation",
    "PrivilegedSystemSession",
    "RegistryError",
    "ReviewedSql",
    "ScanReport",
    "TenantAsyncSession",
    "TenantContextRequired",
    "TenantIsolationError",
    "TenantRebindError",
    "TenantSession",
    "build_registry",
    "infer_isolation",
    "open_privileged_async_session",
    "open_privileged_session",
    "privileged_option",
    "require_tenant_id",
    "reviewed_sql_option",
    "scan_repositories",
]
