"""ERP 身份内省客户端与短时缓存。不直连 ERP MySQL。"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import INTERNAL_SERVICE_HEADER, TENANT_HEADER, TenantContext
from app.schemas.identity import IdentityIntrospectOut


@dataclass
class _CacheEntry:
    context: TenantContext
    expires_at: float


class IdentityCache:
    """按 JWT jti + tenant_id 缓存身份，默认 30 秒，权限变更最多延迟一个 TTL。"""
    """TODO 缓存到 Redis，并定期异步刷新。"""
    """TODO 后续还有考虑多项目怎么办，如果都调用erp项目来获取身份，架构上不合理，需要考虑其他方案"""

    def __init__(self) -> None:
        self._items: dict[tuple[str, int], _CacheEntry] = {}

    def get(self, jti: str, tenant_id: int) -> TenantContext | None:
        entry = self._items.get((jti, tenant_id))
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            self._items.pop((jti, tenant_id), None)
            return None
        return entry.context

    def put(self, context: TenantContext) -> None:
        ttl = max(1, settings.identity_cache_ttl_seconds)
        self._items[(context.token_jti, context.tenant_id)] = _CacheEntry(
            context=context,
            expires_at=time.monotonic() + ttl,
        )


class ErpIdentityClient:
    """调用 ERP 内部身份内省。测试可替换本类，避免打到真实 ERP。"""

    def __init__(self, cache: IdentityCache | None = None) -> None:
        self.cache = cache or IdentityCache()

    async def resolve(self, *, access_token: str, tenant_id: int, jti: str) -> TenantContext:
        cached = self.cache.get(jti, tenant_id)
        if cached is not None:
            return cached
        snapshot = await self.introspect(access_token=access_token, tenant_id=tenant_id)
        if snapshot.user_id <= 0 or snapshot.tenant_id != tenant_id:
            raise AppError("租户不存在或不可访问", code=40410, status_code=404)
        context = TenantContext(
            user_id=snapshot.user_id,
            tenant_id=snapshot.tenant_id,
            member_id=snapshot.member_id,
            is_owner=snapshot.is_owner,
            role=snapshot.role,
            permission_codes=frozenset(snapshot.permission_codes),
            token_jti=snapshot.token_jti or jti,
        )
        self.cache.put(context)
        return context

    async def introspect(self, *, access_token: str, tenant_id: int) -> IdentityIntrospectOut:
        """向 ERP 换取已校验的成员身份与权限编码。"""
        if not settings.erp_internal_service_key:
            raise AppError("内部身份接口未配置", code=50311, status_code=503)
        url = f"{settings.erp_api_base_url.rstrip('/')}/api/v1/internal/identity/introspect"
        try:
            # 服务间调用不走系统 HTTP 代理，避免本机 Clash 等把 Header 剥掉。
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        TENANT_HEADER: str(tenant_id),
                        INTERNAL_SERVICE_HEADER: settings.erp_internal_service_key,
                    },
                )
        except httpx.HTTPError as exc:
            raise AppError("身份服务暂时不可用", code=50310, status_code=503) from exc

        body = _safe_json(response)
        if response.status_code >= 400:
            message = str(body.get("message") or "身份校验失败")
            code = int(body.get("code") or response.status_code)
            raise AppError(message, code=code, status_code=response.status_code)
        data = body.get("data")
        if not isinstance(data, dict):
            raise AppError("身份服务返回异常", code=50310, status_code=503)
        return IdentityIntrospectOut.model_validate(data)

    async def ping(self) -> bool:
        url = f"{settings.erp_api_base_url.rstrip('/')}/api/v1/health"
        try:
            async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                response = await client.get(url)
            return response.status_code < 500
        except httpx.HTTPError:
            return False


def _safe_json(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


identity_client = ErpIdentityClient()
