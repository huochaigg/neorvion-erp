from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation

from app.core.config import settings
from app.core.exceptions import AppError
from app.mcp.security import validate_resolved_endpoint
from app.models.ecosystem import McpServer
from mcp import Client, MCPError


class _UnsafeMcpResponse(RuntimeError):
    """用于从 SDK 的异步任务组中传递出站安全拒绝。"""


class _LimitedAsyncByteStream(httpx2.AsyncByteStream):
    """对 SDK 消费的 SSE/分块响应实施累计字节上限。"""

    def __init__(self, inner: httpx2.AsyncByteStream, limit: int) -> None:
        self.inner = inner
        self.limit = limit

    async def __aiter__(self):
        consumed = 0
        async for chunk in self.inner:
            consumed += len(chunk)
            if consumed > self.limit:
                raise _UnsafeMcpResponse("MCP Server 响应过大")
            yield chunk

    async def aclose(self) -> None:
        await self.inner.aclose()


class StreamableHttpTransport:
    """受控的官方 MCP SDK Streamable HTTP 客户端。

    Registry 和 Gateway 仍是权限边界；SDK 只负责协议协商、工具发现和
    tools/call。网络客户端禁止环境代理、禁止任何重定向，并在请求前重新
    执行 DNS/地址允许检查。生产还必须经过独立 Egress Proxy。
    """

    def __init__(self, server: McpServer) -> None:
        self.server = server

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._execute(lambda client: client.list_tools())
        payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        tools = payload.get("tools")
        if not isinstance(tools, list) or len(tools) > settings.mcp_max_tools_per_server:
            raise AppError("MCP 工具列表无效或过大", code=50281, status_code=502)
        return [item for item in tools if isinstance(item, dict)]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self._execute(lambda client: client.call_tool(name, arguments))
        payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        if not isinstance(payload, dict):
            raise AppError("MCP 工具响应无效", code=50281, status_code=502)
        if result.is_error:
            raise AppError("MCP 工具返回失败", code=50281, status_code=502)
        return payload

    async def _execute(self, operation: Callable[[Client], Awaitable[Any]]) -> Any:
        """每次调用建立可限时释放的 SDK 会话，并将协议异常映射为稳定 API 错误。"""
        self._assert_runtime_gate()
        await validate_resolved_endpoint(self.server.endpoint)
        timeout_seconds = min(self.server.timeout_seconds, settings.mcp_timeout_seconds)
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Origin": settings.mcp_origin,
        }
        if self.server.authentication_type == "BEARER_ENV":
            secret = os.getenv(self.server.credential_reference or "", "")
            if not secret:
                raise AppError("MCP Server 凭据未配置", code=50382, status_code=503)
            headers["Authorization"] = f"Bearer {secret}"

        try:
            async with httpx2.AsyncClient(
                headers=headers,
                timeout=httpx2.Timeout(timeout_seconds, read=timeout_seconds),
                follow_redirects=False,
                max_redirects=0,
                proxy=settings.mcp_egress_proxy_url or None,
                trust_env=False,
                limits=httpx2.Limits(max_connections=4, max_keepalive_connections=2),
                event_hooks={"response": [self._guard_response]},
            ) as http_client:
                transport = streamable_http_client(
                    self.server.endpoint,
                    http_client=http_client,
                    terminate_on_close=True,
                )
                async with Client(
                    transport,
                    read_timeout_seconds=timeout_seconds,
                    client_info=Implementation(
                        name="neorvion-copilot", version=settings.app_version
                    ),
                    raise_exceptions=False,
                ) as client:
                    async with asyncio.timeout(timeout_seconds):
                        return await operation(client)
        except AppError:
            raise
        except TimeoutError as exc:
            raise AppError("MCP Server 调用超时", code=50481, status_code=504) from exc
        except Exception as exc:
            if self._contains_exception(exc, _UnsafeMcpResponse):
                reason = self._find_exception(exc, _UnsafeMcpResponse)
                raise AppError(str(reason), code=40382, status_code=403) from exc
            if self._contains_exception(exc, httpx2.TimeoutException):
                raise AppError("MCP Server 调用超时", code=50481, status_code=504) from exc
            if isinstance(exc, MCPError):
                raise AppError("MCP Server 返回协议错误", code=50281, status_code=502) from exc
            raise AppError("MCP Server 网络或协议不可用", code=50282, status_code=502) from exc

    async def _guard_response(self, response: httpx2.Response) -> None:
        """在 SDK 处理响应前拒绝重定向和过大非流式载荷。"""
        if 300 <= response.status_code < 400:
            raise _UnsafeMcpResponse("MCP 重定向被拒绝")
        content_length = response.headers.get("content-length", "")
        if content_length.isdigit() and int(content_length) > settings.mcp_max_response_bytes:
            raise _UnsafeMcpResponse("MCP Server 响应过大")
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            body = await response.aread()
            if len(body) > settings.mcp_max_response_bytes:
                raise _UnsafeMcpResponse("MCP Server 响应过大")
        else:
            response.stream = _LimitedAsyncByteStream(
                response.stream, settings.mcp_max_response_bytes
            )

    def _assert_runtime_gate(self) -> None:
        if not settings.mcp_remote_execution_enabled:
            raise AppError("远程 MCP 执行未启用", code=50381, status_code=503)
        if settings.is_production and (
            not settings.mcp_network_isolation_acknowledged
            or not settings.mcp_budget_gate_verified
            or not settings.mcp_egress_proxy_url
        ):
            raise AppError("生产 MCP 网络或预算硬门禁未验收", code=50381, status_code=503)

    @classmethod
    def _contains_exception(
        cls, exc: BaseException, expected: type[BaseException] | tuple[type[BaseException], ...]
    ) -> bool:
        return cls._find_exception(exc, expected) is not None

    @classmethod
    def _find_exception(
        cls, exc: BaseException, expected: type[BaseException] | tuple[type[BaseException], ...]
    ) -> BaseException | None:
        if isinstance(exc, expected):
            return exc
        if isinstance(exc, BaseExceptionGroup):
            for child in exc.exceptions:
                found = cls._find_exception(child, expected)
                if found is not None:
                    return found
        return None
