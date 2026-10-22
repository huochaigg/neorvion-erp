from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.ai.types import ModelToolCall
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.erp.client import ErpApiClient
from app.tools.registry import ToolRegistry


@dataclass(slots=True)
class ToolRuntime:
    tenant: TenantContext
    access_token: str
    erp_audience_authorized: bool
    request_id: str = ""
    started_at: float = field(default_factory=time.monotonic)
    calls: int = 0


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    content: str
    event: dict[str, Any]


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, client: ErpApiClient) -> None:
        self.registry = registry
        self.client = client

    async def execute(self, call: ModelToolCall, runtime: ToolRuntime) -> ToolExecutionResult:
        """在模型之外执行工具白名单、参数、权限、预算和结果大小校验。"""
        spec = self.registry.get(call.name)
        if spec is None:
            raise AppError("模型请求了未注册的工具", code=40072, status_code=400)
        if spec.permission not in runtime.tenant.permission_codes:
            raise AppError("无权使用该查询工具", code=40372, status_code=403)
        if not runtime.access_token or not runtime.erp_audience_authorized:
            raise AppError("当前令牌不能代表用户访问 ERP", code=40373, status_code=403)
        if runtime.calls >= settings.tool_max_calls:
            raise AppError("工具调用次数已达上限", code=42972, status_code=429)
        if time.monotonic() - runtime.started_at >= settings.tool_total_timeout_seconds:
            raise AppError("工具执行总时限已到", code=50472, status_code=504)
        try:
            raw_args = json.loads(call.arguments or "{}")
            if not isinstance(raw_args, dict):
                raise ValueError
            args = spec.args_model.model_validate(raw_args)
        except (json.JSONDecodeError, ValueError, ValidationError) as exc:
            raise AppError("工具参数无效", code=40071, status_code=400) from exc
        runtime.calls += 1
        started = time.monotonic()
        remaining = settings.tool_total_timeout_seconds - (started - runtime.started_at)
        try:
            async with asyncio.timeout(max(0.01, remaining)):
                result = await spec.execute(
                    self.client,
                    args,
                    access_token=runtime.access_token,
                    tenant_id=runtime.tenant.tenant_id,
                    request_id=runtime.request_id,
                )
        except TimeoutError as exc:
            raise AppError("工具执行超时", code=50472, status_code=504) from exc
        serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        truncated = len(serialized) > settings.tool_max_result_chars
        if truncated:
            serialized = serialized[: settings.tool_max_result_chars]
        content = "<untrusted_erp_tool_result>\n" + serialized + "\n</untrusted_erp_tool_result>"
        return ToolExecutionResult(
            content=content,
            event={
                "tool_call_id": call.id,
                "name": call.name,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "truncated": truncated,
            },
        )
