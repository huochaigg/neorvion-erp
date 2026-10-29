import pytest
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.mcp.gateway import McpGateway
from app.mcp.security import (
    validate_arguments,
    validate_endpoint,
    validate_resolved_addresses,
    validate_tool_schema,
)
from app.schemas.ecosystem import McpServerOut, SkillRunOut, SkillVersionIn


def test_mcp_response_schemas_never_expose_secret_value() -> None:
    fields = McpServerOut.model_fields
    assert "credential_reference" in fields
    assert "credential_configured" in fields
    assert "credential_value" not in fields
    assert "api_key" not in fields
    assert "access_token" not in fields
    assert "safe_error" in SkillRunOut.model_fields


def test_endpoint_requires_https_allowlist_and_no_query(monkeypatch) -> None:
    monkeypatch.setattr("app.mcp.security.settings.mcp_allowed_hosts", "mcp.example.com")
    assert validate_endpoint("https://mcp.example.com/rpc") == "https://mcp.example.com/rpc"
    for endpoint in (
        "http://mcp.example.com/rpc",
        "https://127.0.0.1/rpc",
        "https://mcp.example.com/rpc?url=http://metadata",
        "https://user:password@mcp.example.com/rpc",
    ):
        with pytest.raises(AppError):
            validate_endpoint(endpoint)


def test_dns_rebinding_private_result_is_rejected() -> None:
    with pytest.raises(AppError):
        validate_resolved_addresses({"10.0.0.2", "93.184.216.34"})


def test_schema_rejects_control_arguments_and_unknown_input() -> None:
    with pytest.raises(AppError):
        validate_tool_schema({"type": "object", "properties": {"url": {"type": "string"}}})
    schema = validate_tool_schema(
        {
            "type": "object",
            "properties": {"sku_code": {"type": "string", "maxLength": 30}},
            "required": ["sku_code"],
        }
    )
    assert validate_arguments(schema, {"sku_code": "SKU-1"}) == {"sku_code": "SKU-1"}
    with pytest.raises(AppError):
        validate_arguments(schema, {"sku_code": "SKU-1", "tenant_id": 7})


def test_skill_is_read_only_and_rejects_executable_instructions() -> None:
    base = {
        "instructions": "根据已授权工具证据生成库存风险摘要。",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "allowed_agents": ["inventory_agent"],
        "required_permissions": [PermissionCode.INVENTORY_READ],
        "allowed_tools": ["analyze_inventory_coverage"],
    }
    assert SkillVersionIn.model_validate(base).risk_level == "READ_ONLY"
    with pytest.raises(ValueError):
        SkillVersionIn.model_validate(base | {"instructions": "执行 ```python\nprint(1)\n```"})


def test_gateway_agent_whitelist_filters_model_definitions() -> None:
    definition = {
        "type": "function",
        "function": {"name": "mcp__risk__lookup", "description": "x", "parameters": {}},
    }
    gateway = McpGateway(
        None, None, (definition,), {"mcp__risk__lookup": frozenset({"inventory_agent"})}
    )  # type: ignore[arg-type]
    assert gateway.definitions("inventory_agent") == [definition]
    assert gateway.definitions("sales_agent") == []
