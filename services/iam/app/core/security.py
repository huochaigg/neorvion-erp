"""密码哈希与 JWT 签发。JWT 密钥与 RSA 传输密钥必须分开。"""

import secrets
import string
from datetime import timedelta
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from neorvion_security.errors import SecurityError
from neorvion_security.jwt import JwtClaims, JwtVerifier

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.jwt_keys import get_jwt_signer

_password_hasher = PasswordHasher()
TokenType = Literal["access", "refresh"]


def generate_temporary_password(*, length: int = 12) -> str:
    """生成一次性临时密码，禁止写日志、禁止入库明文。"""
    alphabet = string.ascii_letters + string.digits
    while True:
        raw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(char.isalpha() for char in raw) and any(char.isdigit() for char in raw):
            return raw


def hash_password(plain_password: str) -> str:
    """生成不可逆存储哈希。明文不得入库、不得写日志。"""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验明文是否匹配 Argon2id。哈希损坏时视为失败。"""
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: int, *, token_version: int) -> str:
    token, _jti = get_jwt_signer().sign(
        user_id=user_id,
        token_type="access",
        ttl=timedelta(seconds=settings.access_token_ttl_seconds()),
        token_version=token_version,
    )
    return token


def create_refresh_token(user_id: int, *, token_version: int) -> tuple[str, str, int]:
    seconds = settings.jwt_refresh_expire_days * 24 * 60 * 60
    token, jti = get_jwt_signer().sign(
        user_id=user_id,
        token_type="refresh",
        ttl=timedelta(seconds=seconds),
        token_version=token_version,
    )
    return token, jti, seconds


def decode_token(token: str, *, expected_type: TokenType) -> JwtClaims:
    """校验 RS256、kid、iss、aud、exp、nbf、sub、jti 与 type。"""
    verifier = JwtVerifier(
        issuer=settings.jwt_issuer,
        audience="neorvion-iam",
        static_keys=_static_verify_keys(),
        leeway_seconds=settings.jwt_leeway_seconds,
    )
    try:
        if expected_type == "access":
            return verifier.verify_access(token)
        return verifier.verify_refresh(token)
    except SecurityError as exc:
        raise AppError(exc.message, code=exc.code, status_code=exc.status_code) from exc


def _static_verify_keys() -> dict:
    """IAM 本进程用本地公钥验签，不走 HTTP JWKS，避免自调用。"""
    from cryptography.hazmat.primitives import serialization

    from app.core.jwt_keys import get_jwt_signer, previous_public_pem

    signer = get_jwt_signer()
    public = serialization.load_pem_public_key(signer.public_pem)
    keys = {signer.kid: public}
    previous = previous_public_pem()
    if previous is not None:
        keys[previous[1]] = serialization.load_pem_public_key(previous[0])
    return keys
