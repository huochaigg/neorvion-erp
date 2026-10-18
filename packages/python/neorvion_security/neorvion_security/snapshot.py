"""IAM 写入、业务服务只读的授权快照。Redis 不可用或版本不一致时拒绝。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from neorvion_security.errors import SecurityError
from neorvion_security.jwt import JwtClaims
from neorvion_security.tenant import TenantContext

SNAPSHOT_PREFIX = "iam:snap:"
TOKEN_VERSION_PREFIX = "iam:tver:"
AUTHZ_VERSION_PREFIX = "iam:aver:"
REFRESH_PREFIX = "iam:refresh:"
CSRF_PREFIX = "iam:csrf:"


class RedisLike(Protocol):
    """兼容 redis-py 同步客户端。方法签名放宽，避免 stubs 把 self 标成异步客户端。"""

    def get(self, name: Any) -> Any: ...
    def set(self, name: Any, value: Any, ex: int | None = None) -> Any: ...
    def delete(self, *names: Any) -> Any: ...
    def incr(self, name: Any) -> Any: ...
    def getdel(self, name: Any) -> Any: ...


def snapshot_key(user_id: int, tenant_id: int) -> str:
    return f"{SNAPSHOT_PREFIX}{user_id}:{tenant_id}"


def token_version_key(user_id: int) -> str:
    return f"{TOKEN_VERSION_PREFIX}{user_id}"


def authz_version_key(user_id: int, tenant_id: int) -> str:
    return f"{AUTHZ_VERSION_PREFIX}{user_id}:{tenant_id}"


def refresh_key(jti: str) -> str:
    return f"{REFRESH_PREFIX}{jti}"


def csrf_key(jti: str) -> str:
    return f"{CSRF_PREFIX}{jti}"


@dataclass(frozen=True, slots=True)
class AuthzSnapshot:
    """IAM 在登录、刷新、角色/成员变更后写入 Redis 的授权快照。"""

    user_id: int
    tenant_id: int
    member_id: int
    is_owner: bool
    role: str
    status: str
    tenant_status: str
    permission_codes: tuple[str, ...]
    role_codes: tuple[str, ...]
    authz_version: int
    token_version: int
    is_platform_admin: bool = False
    must_change_password: bool = False
    display_name: str = ""
    email: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_id": self.user_id,
                "tenant_id": self.tenant_id,
                "member_id": self.member_id,
                "is_owner": self.is_owner,
                "role": self.role,
                "status": self.status,
                "tenant_status": self.tenant_status,
                "permission_codes": list(self.permission_codes),
                "role_codes": list(self.role_codes),
                "authz_version": self.authz_version,
                "token_version": self.token_version,
                "is_platform_admin": self.is_platform_admin,
                "must_change_password": self.must_change_password,
                "display_name": self.display_name,
                "email": self.email,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> AuthzSnapshot:
        data = json.loads(raw)
        return cls(
            user_id=int(data["user_id"]),
            tenant_id=int(data["tenant_id"]),
            member_id=int(data["member_id"]),
            is_owner=bool(data["is_owner"]),
            role=str(data["role"]),
            status=str(data["status"]),
            tenant_status=str(data["tenant_status"]),
            permission_codes=tuple(str(item) for item in data.get("permission_codes") or []),
            role_codes=tuple(str(item) for item in data.get("role_codes") or []),
            authz_version=int(data.get("authz_version") or 0),
            token_version=int(data.get("token_version") or 0),
            is_platform_admin=bool(data.get("is_platform_admin") or False),
            must_change_password=bool(data.get("must_change_password") or False),
            display_name=str(data.get("display_name") or ""),
            email=str(data.get("email") or ""),
        )

    def to_context(self, *, token_jti: str) -> TenantContext:
        return TenantContext(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            member_id=self.member_id,
            is_owner=self.is_owner,
            role=self.role,
            permission_codes=frozenset(self.permission_codes),
            role_codes=self.role_codes,
            token_jti=token_jti,
            token_version=self.token_version,
            authz_version=self.authz_version,
            is_platform_admin=self.is_platform_admin,
            must_change_password=self.must_change_password,
            display_name=self.display_name,
            email=self.email,
            session_id="",
            high_risk_verified=False,
            authz_source="snapshot",
        )


class SnapshotStore:
    """业务服务只读 Redis 快照；IAM 负责写入与版本递增。"""

    def __init__(self, redis: RedisLike, *, ttl_seconds: int = 3600) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def save(self, snapshot: AuthzSnapshot) -> None:
        self.redis.set(
            snapshot_key(snapshot.user_id, snapshot.tenant_id),
            snapshot.to_json(),
            ex=self.ttl_seconds,
        )
        self.redis.set(
            authz_version_key(snapshot.user_id, snapshot.tenant_id),
            str(snapshot.authz_version),
            ex=self.ttl_seconds,
        )
        self.redis.set(
            token_version_key(snapshot.user_id),
            str(snapshot.token_version),
            ex=None,
        )

    def bump_token_version(self, user_id: int) -> int:
        """停用账号、强制下线时递增。未过期 Access Token 随后全部失效。"""
        return int(self.redis.incr(token_version_key(user_id)))

    def bump_authz_version(self, user_id: int, tenant_id: int) -> int:
        """角色、成员权限变更时递增，使旧快照立即失效。"""
        return int(self.redis.incr(authz_version_key(user_id, tenant_id)))

    def set_authz_version(self, user_id: int, tenant_id: int, version: int) -> None:
        """把数据库事务内递增的授权版本写入 Redis，供普通接口比对。"""
        self.redis.set(authz_version_key(user_id, tenant_id), str(int(version)), ex=self.ttl_seconds)

    def current_token_version(self, user_id: int) -> int:
        raw = self.redis.get(token_version_key(user_id))
        return int(raw) if raw is not None else 0

    def load(
        self,
        *,
        claims: JwtClaims,
        tenant_id: int,
        high_risk: bool = False,
        authority: Callable[[], TenantContext] | None = None,
    ) -> TenantContext:
        """读取并校验快照。Redis 失败、缺失或版本不一致时拒绝，不得放行。

        high_risk=True 时必须提供 authority（回源 IAM 数据库）。Pub/Sub 与 Redis
        只能加速失效，不能作为高风险操作的正确性保证。
        """
        if high_risk:
            if authority is None:
                raise SecurityError("高风险操作缺少权威授权通道", code=50314, status_code=503)
            context = authority()
            if not context.high_risk_verified:
                raise SecurityError("高风险操作缺少权威授权通道", code=50314, status_code=503)
            return context
        try:
            stored_ver = self.redis.get(token_version_key(claims.user_id))
            raw = self.redis.get(snapshot_key(claims.user_id, tenant_id))
            aver = self.redis.get(authz_version_key(claims.user_id, tenant_id))
        except Exception as exc:
            raise SecurityError("授权状态暂时不可用", code=50313, status_code=503) from exc
        expected_ver = int(stored_ver) if stored_ver is not None else 0
        if claims.token_version != expected_ver:
            raise SecurityError("登录已失效，请重新登录", code=40104, status_code=401)
        if raw is None:
            raise SecurityError("缺少租户授权快照", code=40310, status_code=403)
        snapshot = AuthzSnapshot.from_json(raw)
        current_aver = int(aver) if aver is not None else snapshot.authz_version
        if snapshot.authz_version != current_aver:
            raise SecurityError("权限已变更，请重新进入企业", code=40321, status_code=403)
        if snapshot.user_id != claims.user_id or snapshot.tenant_id != tenant_id:
            raise SecurityError("租户不存在或不可访问", code=40410, status_code=404)
        if snapshot.status != "ACTIVE":
            raise SecurityError("无权访问该租户", code=40310, status_code=403)
        if snapshot.tenant_status != "ACTIVE":
            raise SecurityError("无权访问该租户", code=40310, status_code=403)
        context = snapshot.to_context(token_jti=claims.jti)
        return TenantContext(
            user_id=context.user_id,
            tenant_id=context.tenant_id,
            member_id=context.member_id,
            is_owner=context.is_owner,
            role=context.role,
            permission_codes=context.permission_codes,
            role_codes=context.role_codes,
            token_jti=context.token_jti,
            token_version=context.token_version,
            authz_version=context.authz_version,
            is_platform_admin=context.is_platform_admin,
            must_change_password=context.must_change_password,
            display_name=context.display_name,
            email=context.email,
            session_id=claims.session_id,
            high_risk_verified=False,
            authz_source="snapshot",
        )

    def load_for_principal(self, *, user_id: int, tenant_id: int) -> TenantContext:
        """Worker / 内部任务按 user_id + tenant_id 还原快照，不解析 JWT。

        Redis 缺失或版本不一致时拒绝，不得在无快照时放行。
        """
        try:
            stored_ver = self.redis.get(token_version_key(user_id))
            raw = self.redis.get(snapshot_key(user_id, tenant_id))
            aver = self.redis.get(authz_version_key(user_id, tenant_id))
        except Exception as exc:
            raise SecurityError("授权状态暂时不可用", code=50313, status_code=503) from exc
        if raw is None:
            raise SecurityError("缺少租户授权快照", code=40310, status_code=403)
        snapshot = AuthzSnapshot.from_json(raw)
        expected_ver = int(stored_ver) if stored_ver is not None else 0
        if snapshot.token_version != expected_ver:
            raise SecurityError("登录已失效，请重新登录", code=40104, status_code=401)
        current_aver = int(aver) if aver is not None else snapshot.authz_version
        if snapshot.authz_version != current_aver:
            raise SecurityError("权限已变更，请重新进入企业", code=40321, status_code=403)
        if snapshot.user_id != user_id or snapshot.tenant_id != tenant_id:
            raise SecurityError("租户不存在或不可访问", code=40410, status_code=404)
        if snapshot.status != "ACTIVE" or snapshot.tenant_status != "ACTIVE":
            raise SecurityError("无权访问该租户", code=40310, status_code=403)
        return snapshot.to_context(token_jti="")

    def require_permissions(
        self,
        context: TenantContext,
        codes: list[str],
        *,
        mode: str = "all",
    ) -> None:
        owned = context.permission_codes
        if mode == "any":
            if not any(code in owned for code in codes):
                raise SecurityError("缺少权限", code=40320, status_code=403)
            return
        missing = [code for code in codes if code not in owned]
        if missing:
            raise SecurityError("缺少权限", code=40320, status_code=403)
