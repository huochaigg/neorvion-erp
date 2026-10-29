from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.mcp.security import validate_resolved_endpoint
from app.models.ecosystem import McpServer


class StreamableHttpTransport:
    """最小 Streamable HTTP JSON-RPC 客户端；远程执行默认关闭且禁止重定向。"""

    def __init__(self, server: McpServer) -> None:
        self.server = server
        self.session_id = ""
        self.request_id = 0

    async def list_tools(self) -> list[dict[str, Any]]:
        await self._initialize()
        result = await self._rpc("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list) or len(tools) > settings.mcp_max_tools_per_server:
            raise AppError("MCP 工具列表无效或过大", code=50281, status_code=502)
        return [item for item in tools if isinstance(item, dict)]

    async def call_tool(self, name: str, arguments: dict) -> dict[str, Any]:
        await self._initialize()
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict):
            raise AppError("MCP 工具响应无效", code=50281, status_code=502)
        return result

    async def _initialize(self) -> None:
        if self.session_id:
            return
        result = await self._rpc(
            "initialize",
            {
                "protocolVersion": settings.mcp_protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "neorvion-copilot", "version": settings.app_version},
            },
        )
        if not isinstance(result, dict):
            raise AppError("MCP initialize 响应无效", code=50281, status_code=502)
        await self._notify("notifications/initialized", {})

    async def _notify(self, method: str, params: dict) -> None:
        await self._request(
            {"jsonrpc": "2.0", "method": method, "params": params},
            expect_response=False,
        )

    async def _rpc(self, method: str, params: dict) -> dict:
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }
        response = await self._request(payload)
        if response.get("error"):
            raise AppError("MCP Server 返回协议错误", code=50281, status_code=502)
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    async def _request(self, payload: dict, *, expect_response: bool = True) -> dict:
        if not settings.mcp_remote_execution_enabled:
            raise AppError("远程 MCP 执行未启用", code=50381, status_code=503)
        if settings.is_production and (
            not settings.mcp_network_isolation_acknowledged
            or not settings.mcp_budget_gate_verified
            or not settings.mcp_egress_proxy_url
        ):
            raise AppError("生产 MCP 网络或预算硬门禁未验收", code=50381, status_code=503)
        await validate_resolved_endpoint(self.server.endpoint)
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Origin": settings.mcp_origin,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.server.authentication_type == "BEARER_ENV":
            secret = os.getenv(self.server.credential_reference or "", "")
            if not secret:
                raise AppError("MCP Server 凭据未配置", code=50382, status_code=503)
            headers["Authorization"] = f"Bearer {secret}"
        try:
            async with httpx.AsyncClient(
                timeout=min(self.server.timeout_seconds, settings.mcp_timeout_seconds),
                follow_redirects=False,
                proxy=settings.mcp_egress_proxy_url or None,
                max_redirects=0,
            ) as client:
                response = None
                for attempt in range(self.server.max_retries + 1):
                    try:
                        response = await client.post(
                            self.server.endpoint, headers=headers, json=payload
                        )
                    except (httpx.TimeoutException, httpx.TransportError):
                        if attempt >= self.server.max_retries:
                            raise
                        await asyncio.sleep(0.1 * (2**attempt))
                        continue
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < self.server.max_retries:
                            await asyncio.sleep(0.1 * (2**attempt))
                            continue
                    break
                if response is None:
                    raise AppError("MCP Server 未返回响应", code=50282, status_code=502)
                if 300 <= response.status_code < 400:
                    raise AppError("MCP 重定向被拒绝", code=40382, status_code=403)
                if response.status_code >= 400:
                    raise AppError("MCP Server 调用失败", code=50282, status_code=502)
                if len(response.content) > settings.mcp_max_response_bytes:
                    raise AppError("MCP Server 响应过大", code=50283, status_code=502)
                self.session_id = response.headers.get("Mcp-Session-Id", self.session_id)
                if not expect_response and (
                    response.status_code in {202, 204} or not response.content
                ):
                    return {}
                return self._decode(response)
        except AppError:
            raise
        except httpx.TimeoutException as exc:
            raise AppError("MCP Server 调用超时", code=50481, status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError("MCP Server 网络不可用", code=50282, status_code=502) from exc

    @staticmethod
    def _decode(response: httpx.Response) -> dict:
        if "text/event-stream" in response.headers.get("content-type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    try:
                        value = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        return value
            raise AppError("MCP SSE 响应无有效事件", code=50281, status_code=502)
        try:
            value = response.json()
        except ValueError as exc:
            raise AppError("MCP JSON 响应无效", code=50281, status_code=502) from exc
        if not isinstance(value, dict):
            raise AppError("MCP JSON 响应无效", code=50281, status_code=502)
        return value
