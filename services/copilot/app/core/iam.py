from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from neorvion_security import JwtVerifier, SnapshotStore
from redis import Redis

from app.core.config import settings

iam_redis_client: Redis = Redis.from_url(settings.iam_redis_url, decode_responses=True)


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

