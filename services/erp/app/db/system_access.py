"""允许打开特权会话的模块。只有 Worker 能领取任务和扫描 Outbox。"""

from neorvion_db import PrivilegedOperation

PRIVILEGED_CALLERS = {
    PrivilegedOperation.WORKER_CLAIM: frozenset({"app.tasks.worker"}),
    PrivilegedOperation.OUTBOX_SCAN: frozenset({"app.tasks.worker"}),
}
