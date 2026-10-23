"""Redis 只投递任务 ID。状态真相在 PostgreSQL。"""

from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


def redis_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def enqueue_task(task_id: int) -> bool:
    """把 task_id 写入 Redis List。Worker 恢复遗留 QUEUED 时即使 API 用 inline 也需要投递。"""
    try:
        await redis_client().lpush(settings.task_queue_key, str(task_id))
        return True
    except RedisError:
        logger.warning("knowledge task enqueue failed task_id=%s", task_id)
        return False


async def enqueue_eval_run(run_id: int) -> bool:
    """评测运行与文档任务共用 Redis List，前缀 eval: 区分。"""
    try:
        await redis_client().lpush(settings.task_queue_key, f"eval:{run_id}")
        return True
    except RedisError:
        logger.warning("knowledge eval enqueue failed run_id=%s", run_id)
        return False


async def enqueue_label_job(job_id: int) -> bool:
    """智能初标 / 批量确认与文档任务共用 Redis List，前缀 label: 区分。"""
    try:
        await redis_client().lpush(settings.task_queue_key, f"label:{job_id}")
        return True
    except RedisError:
        logger.warning("knowledge label enqueue failed job_id=%s", job_id)
        return False


async def pop_queue_item(timeout: int = 2) -> str | None:
    try:
        item = await redis_client().brpop(settings.task_queue_key, timeout=timeout)
    except RedisError:
        logger.warning("knowledge task pop failed")
        return None
    if not item:
        return None
    _key, raw = item
    return str(raw)


async def pop_task(timeout: int = 2) -> int | None:
    raw = await pop_queue_item(timeout=timeout)
    if raw is None or raw.startswith("eval:"):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
