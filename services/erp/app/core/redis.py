from collections.abc import Generator

import redis
from redis import Redis

from app.core.config import settings

redis_client: Redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def get_redis() -> Generator[Redis, None, None]:
    yield redis_client


def ping_redis() -> bool:
    try:
        return bool(redis_client.ping())
    except redis.RedisError:
        return False
