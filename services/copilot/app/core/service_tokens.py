from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx

from app.core.exceptions import AppError


@dataclass(slots=True)
class _CachedToken:
    value: str
    expires_at: float


class ServiceTokenClient:
    """用环境 Secret 换取短期 Token；只在进程内缓存，绝不写入队列或数据库。"""

    def __init__(self, token_url: str, service_id: str, client_secret: str) -> None:
        self.token_url = token_url.rstrip("/")
        self.service_id = service_id
        self.client_secret = client_secret
        self._cache: dict[
            tuple[str, int, tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]],
            _CachedToken,
        ] = {}
        self._lock = asyncio.Lock()

    async def token(
        self,
        *,
        audience: str,
        tenant_id: int,
        scopes: list[str],
        resources: dict[str, list[str]] | None = None,
    ) -> str:
        normalized_resources = tuple(
            sorted(
                (kind, tuple(sorted(set(str(item) for item in values))))
                for kind, values in (resources or {}).items()
            )
        )
        key = (audience, tenant_id, tuple(sorted(set(scopes))), normalized_resources)
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached and cached.expires_at > now + 30:
            return cached.value
        async with self._lock:
            cached = self._cache.get(key)
            if cached and cached.expires_at > time.monotonic() + 30:
                return cached.value
            if not self.token_url or not self.service_id or not self.client_secret:
                raise AppError("后台服务身份未配置，周期任务保持禁用", code=50391, status_code=503)
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        self.token_url,
                        json={
                            "service_id": self.service_id,
                            "client_secret": self.client_secret,
                            "audience": audience,
                            "tenant_id": tenant_id,
                            "scopes": sorted(set(scopes)),
                            "resources": resources or {},
                        },
                    )
            except httpx.HTTPError as exc:
                raise AppError("IAM 服务身份签发暂时不可用", code=50392, status_code=503) from exc
            if response.status_code >= 400:
                raise AppError("IAM 拒绝后台服务身份", code=40392, status_code=403)
            body = response.json()
            data = body.get("data") if isinstance(body, dict) else None
            if not isinstance(data, dict) or not data.get("access_token"):
                raise AppError("IAM 服务身份响应无效", code=50392, status_code=503)
            ttl = max(1, int(data.get("expires_in") or 0))
            value = str(data["access_token"])
            self._cache[key] = _CachedToken(value=value, expires_at=time.monotonic() + ttl)
            return value

    def invalidate(self) -> None:
        self._cache.clear()
