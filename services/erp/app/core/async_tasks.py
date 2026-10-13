"""异步任务类型与状态。长任务不能放在普通 HTTP 请求里同步跑完。"""

from enum import StrEnum

TASK_ID_PREFIX = "tsk_"
TASK_MAX_RETRIES = 3
TASK_QUEUE_KEY = "erp:queue:async-tasks"
EVENT_QUEUE_KEY = "erp:queue:outbox-events"
WORKER_HEARTBEAT_KEY = "erp:worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 15


class TaskType(StrEnum):
    REPORT_EXPORT = "REPORT_EXPORT"
    EVENT_PROCESS = "EVENT_PROCESS"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskLogLevel(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


REPORT_EXPORT_KINDS = frozenset({"sales_trend", "purchase_trend", "low_stock"})
RETRYABLE_STATUSES = frozenset({TaskStatus.FAILED.value, TaskStatus.PENDING.value})
CANCELLABLE_STATUSES = frozenset({TaskStatus.PENDING.value, TaskStatus.QUEUED.value})
