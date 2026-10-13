"""Redis 任务 / Outbox 队列。MySQL 是状态真相，Redis 只投递 id。

选择 Redis List 而不是 Celery：当前 SQLAlchemy 是同步 Session，项目已有 redis-py，
测试可进程内执行 handler。Celery + 额外 broker 对本阶段过重；ARQ 是 asyncio，
和现有 Session 不匹配。
"""

from __future__ import annotations

import logging

from redis import RedisError
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from app.core.async_tasks import EVENT_QUEUE_KEY, TASK_QUEUE_KEY
from app.core.redis import redis_client
from app.services.event_publisher import OUTBOX_SESSION_KEY

logger = logging.getLogger(__name__)


def enqueue_task(task_id: str) -> bool:
    """
    功能：把已落库的 task_id 推入 Redis。
    返回：True 表示入队成功。失败时任务应保持 PENDING，由人工重新入队。
    """
    try:
        redis_client.lpush(TASK_QUEUE_KEY, task_id)
        return True
    except RedisError:
        logger.warning("task enqueue failed task_id=%s", task_id)
        return False


def enqueue_events(event_ids: list[str]) -> None:
    if not event_ids:
        return
    try:
        redis_client.lpush(EVENT_QUEUE_KEY, *event_ids)
    except RedisError:
        logger.warning("outbox enqueue failed count=%s", len(event_ids))


def pop_task(timeout: int = 2) -> str | None:
    try:
        item = redis_client.brpop(TASK_QUEUE_KEY, timeout=timeout)
    except RedisError:
        logger.warning("task queue pop failed")
        return None
    if item is None:
        return None
    _key, task_id = item
    return str(task_id)


def pop_event_ids(limit: int = 20) -> list[str]:
    ids: list[str] = []
    try:
        for _ in range(limit):
            item = redis_client.rpop(EVENT_QUEUE_KEY)
            if item is None:
                break
            ids.append(str(item))
    except RedisError:
        logger.warning("event queue pop failed")
    return ids


@sa_event.listens_for(Session, "after_commit")
def _dispatch_outbox_after_commit(session: Session) -> None:
    """主事务成功后才尝试通知 Worker。Redis 失败不影响已提交的业务和 Outbox 行。"""
    ids = list(session.info.pop(OUTBOX_SESSION_KEY, []) or [])
    enqueue_events(ids)
