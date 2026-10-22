from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError


class ErpApiClient:
    """复用连接的 ERP 只读客户端；身份与租户仍由 ERP 独立校验。"""

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout: float,
        read_timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None,
        access_token: str,
        tenant_id: int,
        request_id: str = "",
    ) -> Any:
        """调用固定 ERP 路径；不接受模型提供的 URL、Token 或租户。"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-ID": str(tenant_id),
        }
        if request_id:
            headers["X-Request-ID"] = request_id
        try:
            response = await self._client.get(
                f"{self.base_url}{path}", params=params, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise AppError("ERP 查询超时", code=50470, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("ERP 服务暂时不可用", code=50270, status_code=502) from exc
        if response.status_code in {401, 403}:
            raise AppError("无权查询该 ERP 数据", code=40370, status_code=403)
        if response.status_code == 404:
            raise AppError("ERP 数据不存在或无权访问", code=40470, status_code=404)
        if response.status_code == 429:
            raise AppError("ERP 查询过于频繁", code=42970, status_code=429)
        if response.status_code >= 500:
            raise AppError("ERP 服务暂时不可用", code=50270, status_code=502)
        if response.status_code >= 400:
            raise AppError("ERP 查询参数无效", code=40070, status_code=400)
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError("ERP 返回了无效响应", code=50271, status_code=502) from exc
        if not isinstance(payload, dict) or payload.get("code") != 0 or "data" not in payload:
            raise AppError("ERP 返回了无效响应", code=50271, status_code=502)
        return payload["data"]

    async def aclose(self) -> None:
        await self._client.aclose()


_client: ErpApiClient | None = None


def get_erp_client() -> ErpApiClient:
    global _client
    if _client is None:
        _client = ErpApiClient(
            base_url=settings.erp_base_url,
            connect_timeout=settings.erp_connect_timeout_seconds,
            read_timeout=settings.erp_read_timeout_seconds,
        )
    return _client


async def close_erp_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
