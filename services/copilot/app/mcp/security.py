from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.exceptions import AppError

_DANGEROUS_ARGUMENTS = {
    "tenant_id",
    "access_token",
    "authorization",
    "api_key",
    "secret",
    "url",
    "endpoint",
    "command",
    "shell",
    "sql",
    "python",
    "code",
}


def _dangerous_argument(name: object) -> bool:
    normalized = str(name).lower().replace("-", "_")
    parts = set(normalized.split("_"))
    return normalized in _DANGEROUS_ARGUMENTS or bool(
        parts
        & {
            "url",
            "endpoint",
            "token",
            "secret",
            "password",
            "authorization",
            "command",
            "shell",
            "sql",
            "python",
        }
    )


def validate_endpoint(endpoint: str) -> str:
    """验证静态 Endpoint；运行前还会解析全部 IP，不能只依赖字符串黑名单。"""
    parsed = urlsplit(endpoint)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise AppError("MCP Endpoint 必须是无内嵌凭据的 HTTPS URL", code=42281, status_code=422)
    if parsed.fragment or parsed.query:
        raise AppError("MCP Endpoint 不允许 query 或 fragment", code=42281, status_code=422)
    allowed = set(settings.mcp_allowed_host_list)
    if not allowed or host not in allowed:
        raise AppError("MCP Endpoint 域名不在部署白名单", code=40381, status_code=403)
    return endpoint.rstrip("/")


async def validate_resolved_endpoint(endpoint: str) -> None:
    """检查 DNS 的全部结果；任何私网、回环、保留或链路本地地址都会拒绝。"""
    host = urlsplit(validate_endpoint(endpoint)).hostname or ""
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AppError("MCP Endpoint DNS 解析失败", code=50381, status_code=503) from exc
    addresses = {item[4][0] for item in infos}
    if not addresses:
        raise AppError("MCP Endpoint 没有可用地址", code=50381, status_code=503)
    validate_resolved_addresses(addresses)


def validate_resolved_addresses(addresses: set[str]) -> None:
    """同步校验解析结果，便于网络层和单元测试复用同一失败关闭规则。"""
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if not address.is_global or address.is_private:
            raise AppError("MCP Endpoint 解析到禁止的网络地址", code=40381, status_code=403)


def validate_tool_schema(schema: object) -> dict:
    """接受可审计的 JSON Schema 子集，拒绝动态引用和危险控制参数。"""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise AppError("MCP 工具输入 Schema 必须是 object", code=42282, status_code=422)
    if any(key in schema for key in ("$ref", "$defs", "oneOf", "anyOf", "allOf", "not")):
        raise AppError("MCP 工具 Schema 使用了不支持的动态结构", code=42282, status_code=422)
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or len(properties) > 50:
        raise AppError("MCP 工具 Schema properties 无效", code=42282, status_code=422)
    for name, value in properties.items():
        if _dangerous_argument(name):
            raise AppError("MCP 工具包含禁止的控制参数", code=42282, status_code=422)
        _validate_schema_node(value, depth=1)
    required = schema.get("required", [])
    if not isinstance(required, list) or not set(required).issubset(properties):
        raise AppError("MCP 工具 Schema required 无效", code=42282, status_code=422)
    normalized = dict(schema)
    normalized["additionalProperties"] = False
    return normalized


def _validate_schema_node(value: object, depth: int) -> None:
    if depth > 5 or not isinstance(value, dict):
        raise AppError("MCP 工具 Schema 过深或无效", code=42282, status_code=422)
    if any(key in value for key in ("$ref", "$defs", "oneOf", "anyOf", "allOf", "not")):
        raise AppError("MCP 工具 Schema 使用了不支持的动态结构", code=42282, status_code=422)
    kind = value.get("type")
    if kind not in {"string", "integer", "number", "boolean", "array", "object"}:
        raise AppError("MCP 工具 Schema 类型不受支持", code=42282, status_code=422)
    if kind == "array":
        _validate_schema_node(value.get("items"), depth + 1)
    if kind == "object":
        props = value.get("properties", {})
        if not isinstance(props, dict) or len(props) > 30:
            raise AppError("MCP 工具嵌套 Schema 无效", code=42282, status_code=422)
        for name, child in props.items():
            if _dangerous_argument(name):
                raise AppError("MCP 工具包含禁止的控制参数", code=42282, status_code=422)
            _validate_schema_node(child, depth + 1)


def validate_arguments(schema: dict, value: object) -> dict:
    if not isinstance(value, dict):
        raise AppError("MCP 工具参数必须是对象", code=40081, status_code=400)
    _validate_value(validate_tool_schema(schema), value, "input")
    return value


def _validate_value(schema: dict, value: object, path: str) -> None:
    kind = schema.get("type")
    checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    if kind in checks and not checks[kind](value):
        raise AppError(f"MCP 工具参数 {path} 类型无效", code=40081, status_code=400)
    if kind == "string" and len(value) > min(int(schema.get("maxLength", 4000)), 4000):
        raise AppError("MCP 工具字符串参数过长", code=40081, status_code=400)
    if kind == "array":
        if len(value) > min(int(schema.get("maxItems", 100)), 100):
            raise AppError("MCP 工具数组参数过长", code=40081, status_code=400)
        for index, item in enumerate(value):
            _validate_value(schema["items"], item, f"{path}[{index}]")
    if kind == "object":
        properties = schema.get("properties", {})
        unknown = set(value) - set(properties)
        if unknown:
            raise AppError("MCP 工具参数包含未声明字段", code=40081, status_code=400)
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise AppError("MCP 工具缺少必填参数", code=40081, status_code=400)
        for name, item in value.items():
            _validate_value(properties[name], item, f"{path}.{name}")
