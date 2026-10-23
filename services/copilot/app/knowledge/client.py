from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError


class KnowledgeApiClient:
    """只调用固定 Knowledge 只读 API，始终透传当前用户身份和已验证租户。"""

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout: float,
        read_timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
            transport=transport,
        )

    async def search(
        self,
        payload: dict[str, Any],
        *,
        access_token: str,
        tenant_id: int,
        request_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/search",
            json=payload,
            params=None,
            access_token=access_token,
            tenant_id=tenant_id,
            request_id=request_id,
        )

    async def list_bases(
        self,
        params: dict[str, Any],
        *,
        access_token: str,
        tenant_id: int,
        request_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/v1/knowledge-bases",
            json=None,
            params=params,
            access_token=access_token,
            tenant_id=tenant_id,
            request_id=request_id,
        )

    async def get_chunk(
        self,
        chunk_id: int,
        *,
        access_token: str,
        tenant_id: int,
        request_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/api/v1/chunks/{chunk_id}",
            json=None,
            params=None,
            access_token=access_token,
            tenant_id=tenant_id,
            request_id=request_id,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None,
        params: dict[str, Any] | None,
        access_token: str,
        tenant_id: int,
        request_id: str,
    ) -> dict[str, Any]:
        """执行固定路径请求并把下游错误映射为不泄露内部响应的业务错误。"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Tenant-ID": str(tenant_id),
        }
        if request_id:
            headers["X-Request-ID"] = request_id
        try:
            response = await self._client.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                params=params,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise AppError("知识库检索超时", code=50474, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("Knowledge 服务暂时不可用", code=50274, status_code=502) from exc
        if response.status_code in {401, 403}:
            raise AppError("无权访问该知识库", code=40374, status_code=403)
        if response.status_code == 404:
            raise AppError("知识来源不存在或已无权访问", code=40474, status_code=404)
        if response.status_code == 429:
            raise AppError("知识库检索过于频繁", code=42974, status_code=429)
        if response.status_code >= 500:
            raise AppError("Knowledge 服务暂时不可用", code=50274, status_code=502)
        if response.status_code >= 400:
            raise AppError("知识库检索参数无效或资源不可访问", code=40074, status_code=400)
        try:
            body = response.json()
        except ValueError as exc:
            raise AppError("Knowledge 返回了无效响应", code=50275, status_code=502) from exc
        if not isinstance(body, dict) or body.get("code") != 0 or not isinstance(body.get("data"), dict):
            raise AppError("Knowledge 返回了无效响应", code=50275, status_code=502)
        return body["data"]

    async def aclose(self) -> None:
        await self._client.aclose()


_client: KnowledgeApiClient | None = None


def get_knowledge_client() -> KnowledgeApiClient:
    global _client
    if _client is None:
        _client = KnowledgeApiClient(
            base_url=settings.knowledge_base_url,
            connect_timeout=settings.knowledge_connect_timeout_seconds,
            read_timeout=settings.knowledge_read_timeout_seconds,
        )
    return _client


async def close_knowledge_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
