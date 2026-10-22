"""Knowledge 特权会话只留给任务 Worker 领取和回收。业务读写使用租户会话。"""

from neorvion_db import PrivilegedOperation

PRIVILEGED_CALLERS = {
    PrivilegedOperation.WORKER_CLAIM: frozenset({"app.tasks.worker"}),
}
