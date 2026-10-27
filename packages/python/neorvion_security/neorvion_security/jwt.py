"""RS256 JWT 校验与测试签发。只允许非对称算法，拒绝 alg=none / HS*。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.request import urlopen
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm

from neorvion_security.errors import SecurityError

ALLOWED_ALGORITHMS = ("RS256",)
TokenType = Literal["access", "refresh"]
SubjectType = Literal["USER", "SERVICE", "DELEGATED"]


@dataclass(frozen=True, slots=True)
class JwtClaims:
    """已通过签名与声明校验的 Access Token 载荷。"""

    user_id: int
    jti: str
    token_type: TokenType
    issuer: str
    audience: tuple[str, ...]
    token_version: int
    issued_at: int
    expires_at: int
    not_before: int
    kid: str
    session_id: str = ""
    subject_type: SubjectType = "USER"
    service_id: str = ""
    tenant_scope: tuple[int, ...] = ()
    scopes: tuple[str, ...] = ()
    resources: dict[str, tuple[str, ...]] = field(default_factory=dict)
    credential_version: int = 0
    actor: str = ""
    delegated_subject: str = ""


class JwksCache:
    """进程内 JWKS 缓存。业务请求不访问 IAM，只读公钥。"""

    def __init__(self, jwks_url: str, *, ttl_seconds: int = 300) -> None:
        self.jwks_url = jwks_url
        self.ttl_seconds = ttl_seconds
        self._expires_at = 0.0
        self._keys: dict[str, PyJWK] = {}

    def get_key(self, kid: str) -> PyJWK:
        now = time.monotonic()
        if now >= self._expires_at or kid not in self._keys:
            self._refresh()
        key = self._keys.get(kid)
        if key is None:
            self._refresh()
            key = self._keys.get(kid)
        if key is None:
            raise SecurityError("签名密钥未知或已轮换", code=40102, status_code=401)
        return key

    def _refresh(self) -> None:
        try:
            with urlopen(self.jwks_url, timeout=3) as response:  # noqa: S310 仅配置的 JWKS URL
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            if not self._keys:
                raise SecurityError("无法加载签名公钥", code=50312, status_code=503) from exc
            # 已有缓存时继续用旧公钥，避免 IAM 短暂不可用导致全站 503。
            self._expires_at = time.monotonic() + min(30, self.ttl_seconds)
            return
        keys: dict[str, PyJWK] = {}
        for item in payload.get("keys") or []:
            kid = str(item.get("kid") or "")
            if not kid:
                continue
            keys[kid] = PyJWK.from_dict(item)
        if not keys:
            raise SecurityError("JWKS 不含可用密钥", code=50312, status_code=503)
        self._keys = keys
        self._expires_at = time.monotonic() + self.ttl_seconds


class JwtVerifier:
    """校验 IAM Access Token：算法、kid、iss、aud、exp、nbf、sub、jti、type。"""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str | None = None,
        jwks_cache: JwksCache | None = None,
        static_keys: dict[str, Any] | None = None,
        leeway_seconds: int = 10,
    ) -> None:
        if not issuer or not audience:
            raise SecurityError("IAM JWT 发行人/受众未配置", code=50013, status_code=500)
        self.issuer = issuer
        self.audience = audience
        self.leeway_seconds = leeway_seconds
        self._static_keys = static_keys or {}
        self._jwks = jwks_cache or (JwksCache(jwks_url) if jwks_url else None)
        if self._jwks is None and not self._static_keys:
            raise SecurityError("未配置 JWKS", code=50013, status_code=500)

    def verify_access(self, token: str) -> JwtClaims:
        return self._verify(token, expected_type="access")

    def verify_refresh(self, token: str) -> JwtClaims:
        return self._verify(token, expected_type="refresh")

    def _verify(self, token: str, *, expected_type: TokenType) -> JwtClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise SecurityError("无效的登录凭证", code=40102, status_code=401) from exc
        alg = header.get("alg")
        kid = str(header.get("kid") or "")
        if alg not in ALLOWED_ALGORITHMS or not kid:
            raise SecurityError("无效的登录凭证", code=40102, status_code=401)
        key = self._static_keys.get(kid)
        if key is None and self._jwks is not None:
            key = self._jwks.get_key(kid).key
        if key is None:
            raise SecurityError("签名密钥未知或已轮换", code=40102, status_code=401)
        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway_seconds,
                options={
                    "require": ["exp", "iat", "nbf", "iss", "aud", "sub", "jti"],
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise SecurityError("登录已过期，请重新登录", code=40103, status_code=401) from exc
        except jwt.InvalidAudienceError as exc:
            raise SecurityError("令牌受众不匹配", code=40106, status_code=401) from exc
        except jwt.InvalidIssuerError as exc:
            raise SecurityError("令牌签发方不匹配", code=40107, status_code=401) from exc
        except jwt.InvalidTokenError as exc:
            raise SecurityError("无效的登录凭证", code=40102, status_code=401) from exc
        if payload.get("type") != expected_type:
            raise SecurityError("无效的登录凭证", code=40102, status_code=401)
        subject_type = str(payload.get("subject_type") or "USER").upper()
        if subject_type not in {"USER", "SERVICE", "DELEGATED"}:
            raise SecurityError("无效的身份类型", code=40108, status_code=401)
        user_id = 0
        service_id = str(payload.get("service_id") or "")
        if subject_type == "SERVICE":
            if expected_type != "access" or not service_id or str(payload["sub"]) != service_id:
                raise SecurityError("无效的服务身份凭证", code=40108, status_code=401)
        else:
            try:
                user_id = int(payload["sub"])
            except (TypeError, ValueError) as exc:
                raise SecurityError("无效的登录凭证", code=40102, status_code=401) from exc
            if user_id <= 0:
                raise SecurityError("无效的登录凭证", code=40102, status_code=401)
        tenant_scope = _positive_int_tuple(payload.get("tenant_scope"))
        scopes = _string_tuple(payload.get("scope"))
        resources = _resource_claim(payload.get("resources"))
        audience = payload.get("aud")
        if isinstance(audience, str):
            aud_tuple = (audience,)
        elif isinstance(audience, list):
            aud_tuple = tuple(str(item) for item in audience)
        else:
            aud_tuple = ()
        if self.audience not in aud_tuple:
            raise SecurityError("令牌受众不匹配", code=40106, status_code=401)
        return JwtClaims(
            user_id=user_id,
            jti=str(payload["jti"]),
            token_type=expected_type,
            issuer=str(payload["iss"]),
            audience=aud_tuple,
            token_version=int(payload.get("ver") or 0),
            issued_at=int(payload["iat"]),
            expires_at=int(payload["exp"]),
            not_before=int(payload["nbf"]),
            kid=kid,
            session_id=str(payload.get("sid") or ""),
            subject_type=subject_type,  # type: ignore[arg-type]
            service_id=service_id,
            tenant_scope=tenant_scope,
            scopes=scopes,
            resources=resources,
            credential_version=int(payload.get("credential_version") or 0),
            actor=str(payload.get("actor") or ""),
            delegated_subject=str(payload.get("delegated_subject") or ""),
        )


class LocalJwtSigner:
    """IAM 与测试用 RS256 签发器。传输 RSA 私钥不得复用本密钥。"""

    def __init__(
        self,
        *,
        private_pem: bytes,
        kid: str,
        issuer: str,
        audiences: list[str],
    ) -> None:
        loaded = serialization.load_pem_private_key(private_pem, password=None)
        if not isinstance(loaded, rsa.RSAPrivateKey):
            raise SecurityError("JWT 签名密钥无效", code=50014, status_code=500)
        self._private = loaded
        self.kid = kid
        self.issuer = issuer
        self.audiences = audiences
        self.public_pem = loaded.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def sign(
        self,
        *,
        user_id: int,
        token_type: TokenType,
        ttl: timedelta,
        token_version: int = 0,
        extra_audiences: list[str] | None = None,
        session_id: str = "",
    ) -> tuple[str, str]:
        now = datetime.now(UTC)
        jti = uuid4().hex
        audiences = list(extra_audiences or self.audiences)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "type": token_type,
            "iss": self.issuer,
            "aud": audiences,
            "iat": now,
            "nbf": now,
            "exp": now + ttl,
            "jti": jti,
            "ver": token_version,
        }
        if session_id:
            payload["sid"] = session_id
        token = jwt.encode(
            payload,
            self._private,
            algorithm="RS256",
            headers={"kid": self.kid, "typ": "JWT"},
        )
        return token, jti

    def sign_service(
        self,
        *,
        service_id: str,
        ttl: timedelta,
        audiences: list[str],
        tenant_scope: list[int],
        scopes: list[str],
        resources: dict[str, list[str]] | None = None,
        credential_version: int = 1,
    ) -> tuple[str, str]:
        """签发短期 SERVICE Token；所有能力均显式写入受签名声明。"""
        if not service_id or not audiences or not tenant_scope or not scopes:
            raise SecurityError("服务身份授权范围不能为空", code=40070, status_code=400)
        now = datetime.now(UTC)
        jti = uuid4().hex
        payload: dict[str, Any] = {
            "sub": service_id,
            "service_id": service_id,
            "subject_type": "SERVICE",
            "type": "access",
            "iss": self.issuer,
            "aud": list(audiences),
            "iat": now,
            "nbf": now,
            "exp": now + ttl,
            "jti": jti,
            "tenant_scope": sorted(set(tenant_scope)),
            "scope": sorted(set(scopes)),
            "resources": resources or {},
            "credential_version": credential_version,
        }
        token = jwt.encode(
            payload,
            self._private,
            algorithm="RS256",
            headers={"kid": self.kid, "typ": "JWT"},
        )
        return token, jti

    def jwks(
        self, previous_public_pem: bytes | None = None, previous_kid: str | None = None
    ) -> dict:
        """当前与上一把公钥的 JWKS，供 /.well-known/jwks.json 使用。"""
        keys = [self._jwk(self.public_pem, self.kid)]
        if previous_public_pem and previous_kid:
            keys.append(self._jwk(previous_public_pem, previous_kid))
        return {"keys": keys}

    @staticmethod
    def _jwk(public_pem: bytes, kid: str) -> dict[str, str]:
        public_key = serialization.load_pem_public_key(public_pem)
        data = json.loads(RSAAlgorithm.to_jwk(public_key))
        data.update({"kid": kid, "use": "sig", "alg": "RS256"})
        return data


def decode_access_token(verifier: JwtVerifier, token: str) -> JwtClaims:
    """业务服务入口：只接受 access。"""
    return verifier.verify_access(token)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item for item in value.split() if item)
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item))
    return ()


def _positive_int_tuple(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    parsed: list[int] = []
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0:
            parsed.append(number)
    return tuple(parsed)


def _resource_claim(value: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _string_tuple(items)
        for key, items in value.items()
        if isinstance(items, (list, str))
    }
