"""IAM JWT 校验与 Redis 授权快照。Knowledge 不访问 ERP 身份内省。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from redis import Redis

from app.core.config import settings
from neorvion_security import JwtVerifier, LocalJwtSigner, SnapshotStore

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
    jwks_url = settings.iam_jwks_url.strip() or None
    return JwtVerifier(
        issuer=settings.iam_jwt_issuer,
        audience=settings.iam_jwt_audience,
        jwks_url=jwks_url,
        static_keys=static or None,
    )


@lru_cache
def snapshot_store() -> SnapshotStore:
    return SnapshotStore(iam_redis_client, ttl_seconds=settings.iam_snapshot_ttl_seconds)


@lru_cache
def test_signer() -> LocalJwtSigner:
    if not settings.iam_jwt_private_key_path:
        raise RuntimeError("未配置测试用 JWT 私钥")
    pem = Path(settings.iam_jwt_private_key_path).read_bytes()
    return LocalJwtSigner(
        private_pem=pem,
        kid=settings.iam_jwt_key_id,
        issuer=settings.iam_jwt_issuer,
        audiences=[settings.iam_jwt_audience],
    )


def ping_iam_store() -> bool:
    """快照 Redis 可达即认为身份依赖可用；不访问 IAM HTTP。"""
    try:
        return bool(iam_redis_client.ping())
    except Exception:
        return False
