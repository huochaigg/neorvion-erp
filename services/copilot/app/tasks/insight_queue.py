import logging

from redis.exceptions import RedisError

from app.core.config import settings
from app.tasks.queue import async_redis

logger = logging.getLogger(__name__)


async def enqueue_insight(tenant_id: int, run_id: int) -> bool:
    """队列仅保存租户与运行 ID，Service Token 永不进入 Redis。"""
    try:
        await async_redis().lpush(
            settings.insight_queue_key, f"{tenant_id}:{run_id}"
        )
        return True
    except RedisError:
        logger.warning("insight enqueue unavailable tenant_id=%s run_id=%s", tenant_id, run_id)
        return False


async def pop_insight(timeout: int = 3) -> tuple[int, int] | None:
    try:
        item = await async_redis().brpop(settings.insight_queue_key, timeout=timeout)
    except RedisError:
        return None
    if not item:
        return None
    try:
        tenant, run_id = item[1].split(":", 1)
        return int(tenant), int(run_id)
    except (ValueError, IndexError):
        logger.warning("discard invalid insight queue item")
        return None
