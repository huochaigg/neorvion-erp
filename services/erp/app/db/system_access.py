"""允许打开特权会话的模块。V1 的生产路径不会调用 open_privileged_session。"""

from neorvion_db import PrivilegedOperation

PRIVILEGED_CALLERS = {
    PrivilegedOperation.WORKER_CLAIM: frozenset({"app.tasks.worker"}),
    PrivilegedOperation.OUTBOX_SCAN: frozenset({"app.tasks.worker"}),
}
