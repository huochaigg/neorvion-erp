"""Worker 与 Outbox 的全局领取。只给特权会话使用，业务查询不要调用这里。"""

from datetime import datetime

from neorvion_db import PrivilegedOperation, privileged_option
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.async_tasks import TaskStatus
from app.core.events import EventStatus
from app.models.async_task import AsyncTask
from app.models.system_event import SystemEvent


def lock_task_for_worker(session: Session, task_id: str) -> AsyncTask | None:
    """按全局 task_id 锁住排队任务。调用方再用行上的 tenant_id 打开业务会话。"""
    stmt = (
        select(AsyncTask)
        .where(
            AsyncTask.task_id == task_id,
            AsyncTask.status.in_((TaskStatus.QUEUED.value, TaskStatus.PENDING.value)),
        )
        .with_for_update(skip_locked=True)
        .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
    )
    return session.execute(stmt).scalar_one_or_none()


def claim_pending_events(session: Session, limit: int = 20) -> list[SystemEvent]:
    """领取待处理 Outbox。事件行自带可空 tenant_id，随后按行进入租户会话。"""
    now = datetime.now()
    stmt = (
        select(SystemEvent)
        .where(
            SystemEvent.status == EventStatus.PENDING.value,
            or_(SystemEvent.next_retry_at.is_(None), SystemEvent.next_retry_at <= now),
        )
        .order_by(SystemEvent.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
        .execution_options(**privileged_option(PrivilegedOperation.OUTBOX_SCAN))
    )
    return list(session.execute(stmt).scalars())
