"""业务服务在高风险操作时回源 IAM 数据库授权，而不是只信 Redis 快照。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from neorvion_security.errors import SecurityError
from neorvion_security.tenant import TenantContext

AuthorityFn = Callable[[], TenantContext]


class HttpAuthorityClient:
    """调用 IAM POST /api/v1/internal/authorize。IAM 或网络故障时拒绝，不得放行。"""

    def __init__(self, *, url: str, internal_key: str, timeout_seconds: float = 3.0) -> None:
        self.url = url
        self.internal_key = internal_key
        self.timeout_seconds = timeout_seconds

    def authorize(
        self,
        *,
        access_token: str,
        tenant_id: int,
        codes: list[str] | None = None,
    ) -> TenantContext:
        """用当前 Access Token 向 IAM 索取最新成员授权。

        参数：业务服务已本地验签的 token、X-Tenant-ID、可选权限编码。
        返回：带 high_risk_verified=True 的 TenantContext。
        异常：IAM 不可达、密钥无效、成员无效或权限不足时 SecurityError。
        """
        if not self.url or not self.internal_key:
            raise SecurityError("高风险操作缺少权威授权通道", code=50314, status_code=503)
        body = json.dumps({"codes": codes or [], "high_risk": True}).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Tenant-ID": str(tenant_id),
                "X-Internal-Key": self.internal_key,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 仅配置的 IAM URL
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = _read_http_error(exc)
            raise SecurityError(
                str(detail.get("message") or "权威授权被拒绝"),
                code=int(detail.get("code") or 40320),
                status_code=int(exc.code or 403),
            ) from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise SecurityError("权威授权暂时不可用", code=50313, status_code=503) from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise SecurityError("权威授权响应无效", code=50313, status_code=503)
        return _context_from_authority(data)


def _read_http_error(exc: HTTPError) -> dict[str, Any]:
    try:
        raw = exc.read().decode("utf-8")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _context_from_authority(data: dict[str, Any]) -> TenantContext:
    codes = data.get("permission_codes") or []
    roles = data.get("role_codes") or []
    return TenantContext(
        user_id=int(data["user_id"]),
        tenant_id=int(data["tenant_id"]),
        member_id=int(data["member_id"]),
        is_owner=bool(data.get("is_owner")),
        role=str(data.get("role") or "MEMBER"),
        permission_codes=frozenset(str(item) for item in codes),
        role_codes=tuple(str(item) for item in roles),
        token_jti=str(data.get("token_jti") or ""),
        token_version=int(data.get("token_version") or 0),
        authz_version=int(data.get("authz_version") or 0),
        is_platform_admin=bool(data.get("is_platform_admin")),
        must_change_password=bool(data.get("must_change_password")),
        display_name=str(data.get("display_name") or ""),
        email=str(data.get("email") or ""),
        session_id=str(data.get("session_id") or ""),
        high_risk_verified=True,
        authz_source="iam-db",
    )
