"""Refresh / CSRF 会话。只存 jti 与 user_id，不把 JWT 原文写入 Redis。"""

import secrets

from neorvion_security.snapshot import csrf_key, refresh_key

from app.core.config import settings
from app.core.redis import redis_client


def save_refresh_session(*, jti: str, user_id: int, ttl_seconds: int, csrf_token: str) -> None:
    redis_client.set(refresh_key(jti), str(user_id), ex=ttl_seconds)
    redis_client.set(csrf_key(jti), csrf_token, ex=ttl_seconds)


def consume_refresh_session(jti: str) -> tuple[int, str] | None:
    """GETDEL：并发刷新时只有一个请求能拿到旧会话。"""
    user_id = redis_client.getdel(refresh_key(jti))
    csrf = redis_client.getdel(csrf_key(jti))
    if user_id is None:
        return None
    return int(user_id), str(csrf or "")


def revoke_refresh_session(jti: str) -> None:
    redis_client.delete(refresh_key(jti), csrf_key(jti))


def peek_csrf(jti: str) -> str | None:
    value = redis_client.get(csrf_key(jti))
    return str(value) if value is not None else None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def cookie_max_age() -> int:
    return settings.jwt_refresh_expire_days * 24 * 60 * 60
