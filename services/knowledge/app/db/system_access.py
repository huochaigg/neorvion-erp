"""Knowledge 特权会话只留给任务 Worker。V1 不替换现有 AsyncSession。"""

from neorvion_db import PrivilegedOperation

PRIVILEGED_CALLERS = {
    PrivilegedOperation.WORKER_CLAIM: frozenset({"app.tasks.worker"}),
}
