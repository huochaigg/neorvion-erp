"""IAM 特权会话只留给授权 outbox 扫描。全局身份查询走 GlobalIdentitySession。"""

from neorvion_db import PrivilegedOperation

PRIVILEGED_CALLERS = {
    PrivilegedOperation.OUTBOX_SCAN: frozenset({"app.services.snapshots"}),
}

PRIVILEGED_FLUSH_MODELS = {
    PrivilegedOperation.OUTBOX_SCAN: frozenset({"AuthzOutbox"}),
}
