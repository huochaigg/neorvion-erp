"""密码哈希与 JWT 签发/校验。密钥只从环境变量读取。"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.exceptions import AppError

# Argon2id 是当前推荐的密码哈希算法，由 PasswordHasher 默认启用。
# 不要用 MD5/SHA-256 直接入库：它们算得太快，容易被撞库。
_password_hasher = PasswordHasher()

TokenType = Literal["access", "refresh"]


def digest_password(plain_password: str) -> str:
    """传输层摘要：SHA-256(明文) 的十六进制。

    前端注册/登录先算这一步，请求体里不再出现明文密码。
    这不是存储哈希。入库仍然必须再走 hash_password()（Argon2id）。
    不用 MD5：MD5 已不适合保护口令。
    """
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest()


def hash_password(password_digest: str) -> str:
    """生成不可逆存储哈希。明文和传输摘要都不得入库、不得写日志。"""
    return _password_hasher.hash(password_digest)


def verify_password(password_digest: str, password_hash: str) -> bool:
    """校验传输摘要是否匹配库中的 Argon2id。哈希损坏时视为失败。"""
    try:
        return _password_hasher.verify(password_hash, password_digest)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(
    *,
    user_id: int,
    token_type: TokenType,
    expires_delta: timedelta,
) -> tuple[str, str]:
    """签发 JWT，返回 (token, jti)。

    Payload 固定包含 sub / type / iat / exp / jti。
    Access 与 Refresh 使用同一密钥，但必须靠 type 字段区分用途。
    """
    now = datetime.now(UTC)
    jti = uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def create_access_token(user_id: int) -> str:
    token, _jti = create_token(
        user_id=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt_access_expire_minutes),
    )
    return token


def create_refresh_token(user_id: int) -> tuple[str, str, int]:
    """返回 refresh token、jti 以及 Redis/Cookie 过期秒数。"""
    seconds = settings.jwt_refresh_expire_days * 24 * 60 * 60
    token, jti = create_token(
        user_id=user_id,
        token_type="refresh",
        expires_delta=timedelta(seconds=seconds),
    )
    return token, jti, seconds


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """校验签名、过期时间和 token 类型。Refresh 不能当作 Access 使用。"""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("登录已过期，请重新登录", code=40103, status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError("无效的登录凭证", code=40102, status_code=401) from exc

    if payload.get("type") != expected_type:
        raise AppError("无效的登录凭证", code=40102, status_code=401)

    subject = payload.get("sub")
    jti = payload.get("jti")
    if not subject or not jti:
        raise AppError("无效的登录凭证", code=40102, status_code=401)
    return payload
