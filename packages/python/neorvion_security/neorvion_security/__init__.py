"""跨服务共享的身份校验组件。禁止在此包中放入 ERP / Knowledge 业务模型。"""

from neorvion_security.errors import SecurityError
from neorvion_security.jwt import JwtClaims, JwtVerifier, LocalJwtSigner, decode_access_token
from neorvion_security.snapshot import (
    AuthzSnapshot,
    SnapshotStore,
    snapshot_key,
    token_version_key,
)
from neorvion_security.tenant import TENANT_HEADER, TenantContext

__all__ = [
    "AuthzSnapshot",
    "JwtClaims",
    "JwtVerifier",
    "LocalJwtSigner",
    "SecurityError",
    "SnapshotStore",
    "TENANT_HEADER",
    "TenantContext",
    "decode_access_token",
    "snapshot_key",
    "token_version_key",
]
