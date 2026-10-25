import logging
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)
_client: Redis | None = None


def redis_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(settings.workflow_redis_url, decode_responses=True)
    return _client


async def enqueue_workflow(tenant_id: int, workflow_id: int) -> bool:
    """Redis 仅投递租户和任务 ID；业务状态仍由 PostgreSQL 决定。"""
    try:
        await cast(Any, redis_client()).lpush(
            settings.workflow_queue_key, f"{tenant_id}:{workflow_id}"
        )
        return True
    except RedisError:
        logger.warning(
            "workflow enqueue unavailable tenant_id=%s workflow_id=%s", tenant_id, workflow_id
        )
        return False


async def pop_workflow(timeout: int = 3) -> tuple[int, int] | None:
    try:
        item = await cast(Any, redis_client()).brpop(
            settings.workflow_queue_key, timeout=timeout
        )
    except RedisError:
        return None
    if not item:
        return None
    try:
        tenant, workflow = item[1].split(":", 1)
        return int(tenant), int(workflow)
    except (ValueError, IndexError):
        logger.warning("discard invalid workflow queue item")
        return None
