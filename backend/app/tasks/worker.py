"""Worker：消费 Redis 任务队列，并扫描 Outbox PENDING 事件。

不要用 FastAPI BackgroundTasks 跑关键长任务：进程重启会丢。
本 Worker 可独立进程运行：uv run python -m app.tasks.worker
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.async_tasks import TASK_QUEUE_KEY, TaskStatus
from app.core.events import EVENT_MAX_RETRIES, AggregateType, EventSource, EventStatus, EventType
from app.core.redis import redis_client
from app.core.sanitize import public_error_message
from app.db.session import SessionLocal
from app.models.async_task import AsyncTask
from app.repositories.async_task import lock_task_for_worker
from app.repositories.system_event import claim_pending_events
from app.services.event_publisher import EventPublisher
from app.tasks.handlers import HANDLERS, append_log
from app.tasks.queue import pop_task

logger = logging.getLogger(__name__)


def process_outbox(session: Session, limit: int = 20) -> int:
    """
    功能：领取 PENDING 事件并标记 PROCESSED。
    第一版消费者只验证 Outbox 生命周期，不发通知、不调大模型。
    幂等：按 event_id 唯一；SKIP LOCKED 避免多 Worker 重复领取。
    """
    events = claim_pending_events(session, limit)
    processed = 0
    for event in events:
        event.status = EventStatus.PROCESSING.value
        session.flush()
        try:
            event.status = EventStatus.PROCESSED.value
            event.processed_at = datetime.now()
            event.last_error = None
            processed += 1
        except Exception as exc:
            event.retry_count += 1
            event.last_error = public_error_message(exc)
            if event.retry_count >= EVENT_MAX_RETRIES:
                event.status = EventStatus.FAILED.value
            else:
                event.status = EventStatus.PENDING.value
                event.next_retry_at = datetime.now() + timedelta(seconds=30)
    if events:
        session.commit()
    return processed


def _complete_task(session: Session, task: AsyncTask, result: dict) -> None:
    task.status = TaskStatus.SUCCESS.value
    task.progress = 100
    task.result = result
    task.error_message = None
    task.finished_at = datetime.now()
    append_log(session, task, "任务完成")
    EventPublisher(session, task.tenant_id).record(
        event_type=EventType.TASK_COMPLETED,
        aggregate_type=AggregateType.TASK,
        aggregate_id=task.id,
        event_source=EventSource.TASK.value,
        payload={"task_id": task.task_id, "task_type": task.task_type},
    )


def _fail_task(session: Session, task: AsyncTask, exc: BaseException) -> None:
    task.status = TaskStatus.FAILED.value
    task.error_message = public_error_message(exc)
    task.finished_at = datetime.now()
    append_log(session, task, task.error_message or "任务失败", level="ERROR")
    EventPublisher(session, task.tenant_id).record(
        event_type=EventType.TASK_FAILED,
        aggregate_type=AggregateType.TASK,
        aggregate_id=task.id,
        event_source=EventSource.TASK.value,
        severity="ERROR",
        payload={"task_id": task.task_id, "task_type": task.task_type},
        message=task.error_message,
    )


def _lock_running(session: Session, task_id: str) -> AsyncTask | None:
    return session.execute(
        select(AsyncTask).where(AsyncTask.task_id == task_id).with_for_update()
    ).scalar_one_or_none()


def execute_task(task_id: str) -> str:
    """
    功能：领取并执行一条任务。测试和生产 Worker 共用。
    返回：最终 status。找不到可领取任务时返回 CANCELLED（表示未执行）。
    并发：FOR UPDATE SKIP LOCKED，已被其他人领取则跳过。
    """
    claim = SessionLocal()
    try:
        task = lock_task_for_worker(claim, task_id)
        if task is None:
            claim.rollback()
            return TaskStatus.CANCELLED.value
        if task.status == TaskStatus.RUNNING.value:
            claim.rollback()
            return TaskStatus.RUNNING.value
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.now()
        task.progress = max(task.progress, 5)
        append_log(claim, task, "任务开始执行")
        claim.commit()
    except Exception:
        claim.rollback()
        raise
    finally:
        claim.close()

    session = SessionLocal()
    try:
        task = _lock_running(session, task_id)
        if task is None:
            session.rollback()
            return TaskStatus.CANCELLED.value
        handler = HANDLERS.get(task.task_type)
        if handler is None:
            raise RuntimeError("unsupported task type")
        result = handler(session, task)
        _complete_task(session, task, result)
        session.commit()
        return TaskStatus.SUCCESS.value
    except Exception as exc:
        session.rollback()
        fail = SessionLocal()
        try:
            task = _lock_running(fail, task_id)
            if task is not None:
                _fail_task(fail, task, exc)
                fail.commit()
        except Exception:
            fail.rollback()
            logger.exception("fail_task persist error task_id=%s", task_id)
        finally:
            fail.close()
        return TaskStatus.FAILED.value
    finally:
        session.close()


def run_once(*, block_seconds: int = 0) -> None:
    """处理一批 Outbox，并尝试领取一条任务。block_seconds=0 时不等待 Redis。"""
    session = SessionLocal()
    try:
        process_outbox(session)
    except Exception:
        session.rollback()
        logger.exception("outbox processing failed")
    finally:
        session.close()

    if block_seconds <= 0:
        raw = redis_client.rpop(TASK_QUEUE_KEY)
        task_id = str(raw) if raw else None
    else:
        task_id = pop_task(timeout=block_seconds)
    if task_id:
        execute_task(task_id)


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("async worker started")
    while True:
        try:
            run_once(block_seconds=2)
        except Exception:
            logger.exception("worker loop error")
            time.sleep(1)
