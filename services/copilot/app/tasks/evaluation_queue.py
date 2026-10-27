import logging
from typing import Any, cast

from redis.exceptions import RedisError

from app.core.config import settings
from app.tasks.queue import redis_client

logger = logging.getLogger(__name__)


async def enqueue_evaluation(tenant_id: int, user_id: int, run_id: int) -> bool:
    """评测队列仅保存非敏感标识；JWT、Prompt 与密钥不会进入 Redis。"""
    try:
        await cast(Any, redis_client()).lpush(
            settings.evaluation_queue_key, f"{tenant_id}:{user_id}:{run_id}"
        )
        return True
    except RedisError:
        logger.warning("evaluation enqueue unavailable tenant_id=%s run_id=%s", tenant_id, run_id)
        return False


async def pop_evaluation(timeout: int = 3) -> tuple[int, int, int] | None:
    try:
        item = await cast(Any, redis_client()).brpop(settings.evaluation_queue_key, timeout=timeout)
    except RedisError:
        return None
    if not item:
        return None
    try:
        tenant, user, run = item[1].split(":", 2)
        return int(tenant), int(user), int(run)
    except (ValueError, IndexError):
        logger.warning("discard invalid evaluation queue item")
        return None
