from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from neorvion_security import JwtVerifier, SnapshotStore
from redis import Redis

from app.core.config import settings

iam_redis_client: Redis = Redis.from_url(
    settings.iam_redis_url,
    decode_responses=True,
    socket_connect_timeout=settings.iam_redis_connect_timeout_seconds,
    socket_timeout=settings.iam_redis_read_timeout_seconds,
    retry_on_timeout=False,
    health_check_interval=30,
)


async def verify_tenant_access(token: str, tenant_id: int):
    """在线程中执行同步 JWKS/Redis 校验，并给整个认证阶段设置硬超时。"""

    def verify():
        claims = jwt_verifier().verify_access(token)
        return claims, snapshot_store().load(claims=claims, tenant_id=tenant_id)

    return await asyncio.wait_for(
        asyncio.to_thread(verify),
        timeout=settings.iam_auth_timeout_seconds,
    )


def _load_public_keys() -> dict:
    keys: dict = {}
    if settings.iam_jwt_public_key_path:
        pem = Path(settings.iam_jwt_public_key_path).read_bytes()
        keys[settings.iam_jwt_key_id] = serialization.load_pem_public_key(pem)
    return keys


@lru_cache
def jwt_verifier() -> JwtVerifier:
    static = _load_public_keys()
    return JwtVerifier(
        issuer=settings.iam_jwt_issuer,
        audience=settings.iam_jwt_audience,
        jwks_url=settings.iam_jwks_url.strip() or None,
        static_keys=static or None,
    )


@lru_cache
def snapshot_store() -> SnapshotStore:
    return SnapshotStore(iam_redis_client, ttl_seconds=settings.iam_snapshot_ttl_seconds)


def ping_iam_store() -> bool:
    try:
        return bool(iam_redis_client.ping())
    except Exception:
        return False
