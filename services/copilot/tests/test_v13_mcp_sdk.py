import httpx2
import pytest
from app.mcp.transport import StreamableHttpTransport, _UnsafeMcpResponse
from mcp.server import MCPServer

from mcp import Client


@pytest.mark.asyncio
async def test_official_mcp_sdk_discovers_and_calls_controlled_tool() -> None:
    server = MCPServer("neorvion-controlled-test")

    @server.tool()
    def lookup_inventory(sku_code: str) -> dict[str, str | int]:
        """只读的受控测试工具，用于验证官方 SDK 的发现与调用协议。"""
        return {"sku_code": sku_code, "available_quantity": 12}

    async with Client(server) as client:
        listed = await client.list_tools()
        called = await client.call_tool("lookup_inventory", {"sku_code": "SKU-001"})

    assert [tool.name for tool in listed.tools] == ["lookup_inventory"]
    assert called.is_error is False
    assert called.structured_content == {"sku_code": "SKU-001", "available_quantity": 12}


@pytest.mark.asyncio
async def test_mcp_transport_rejects_redirect_before_sdk_can_follow_it() -> None:
    transport = object.__new__(StreamableHttpTransport)
    response = httpx2.Response(
        307,
        headers={"location": "https://mcp.example.com/other"},
        request=httpx2.Request("POST", "https://mcp.example.com/mcp"),
    )
    with pytest.raises(_UnsafeMcpResponse, match="重定向"):
        await transport._guard_response(response)
