"""Refresh Token 会话。只存 jti 与 user_id，不把 JWT 原文写入 Redis。"""

from app.core.redis import redis_client

_REFRESH_KEY_PREFIX = "auth:refresh:"


def _key(jti: str) -> str:
    return f"{_REFRESH_KEY_PREFIX}{jti}"


def save_refresh_session(*, jti: str, user_id: int, ttl_seconds: int) -> None:
    redis_client.set(_key(jti), str(user_id), ex=ttl_seconds)


def consume_refresh_session(jti: str) -> int | None:
    """GETDEL：并发刷新时只有一个请求能拿到旧会话。"""
    value = redis_client.getdel(_key(jti))
    if value is None:
        return None
    return int(value)


def revoke_refresh_session(jti: str) -> None:
    redis_client.delete(_key(jti))
