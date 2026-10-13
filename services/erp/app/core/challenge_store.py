"""一次性 RSA challenge。仅存 challenge_id → key_id，验证时原子消费。"""

from uuid import uuid4

from app.core.config import settings
from app.core.redis import redis_client

_CHALLENGE_PREFIX = "auth:challenge:"


def _key(challenge_id: str) -> str:
    return f"{_CHALLENGE_PREFIX}{challenge_id}"


def issue_challenge(key_id: str) -> str:
    """签发一次性 challenge，并与当前公钥 key_id 绑定。"""
    challenge_id = uuid4().hex
    redis_client.set(
        _key(challenge_id),
        key_id,
        ex=settings.rsa_challenge_ttl_seconds,
    )
    return challenge_id


def consume_challenge(challenge_id: str) -> str | None:
    """GETDEL：不存在、过期或已使用都返回 None。"""
    value = redis_client.getdel(_key(challenge_id))
    if value is None:
        return None
    return str(value)
