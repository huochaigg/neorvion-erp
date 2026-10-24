from __future__ import annotations

import json
import re

import httpx

from app.core.exceptions import AppError

_SECRET = re.compile(r"(sk-[A-Za-z0-9._\-]+)|(Bearer\s+\S+)", re.IGNORECASE)


def redact_secrets(text: str) -> str:
    return _SECRET.sub("[redacted]", text)


def classify_model_http_error(status: int, body: str) -> AppError:
    """将供应商 HTTP 错误映射为稳定业务错误，响应中不回显密钥或原始凭证。"""
    safe = redact_secrets(body or "")
    message = ""
    try:
        payload = json.loads(body or "")
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        raw_error = payload.get("error")
        error = raw_error if isinstance(raw_error, dict) else {}
        message = str(payload.get("message") or error.get("message") or "")
    detail = redact_secrets(message).strip()[:160]
    if status == 429:
        return AppError("模型服务限流，请稍后重试", code=42960, status_code=429)
    if status in {408, 504}:
        return AppError("模型服务响应超时", code=50460, status_code=504)
    if status in {401, 403}:
        return AppError("模型服务认证或授权失败", code=40160, status_code=502)
    if status >= 500:
        suffix = f"：{detail}" if detail else ""
        return AppError(
            f"模型服务暂时不可用（HTTP {status}）{suffix}",
            code=50260,
            status_code=502,
        )
    suffix = detail or safe[:160] or "请检查模型配置"
    return AppError(
        f"模型请求被拒绝（HTTP {status}）：{suffix}",
        code=40094,
        status_code=400,
    )


def describe_model_transport(exc: httpx.HTTPError) -> AppError:
    name = type(exc).__name__
    if isinstance(exc, httpx.ConnectTimeout):
        return AppError("连接模型服务超时", code=50461, status_code=504)
    if isinstance(exc, httpx.ReadTimeout):
        return AppError("等待模型服务响应超时", code=50462, status_code=504)
    if isinstance(exc, httpx.TimeoutException):
        return AppError("模型服务请求超时", code=50460, status_code=504)
    if isinstance(exc, httpx.ConnectError):
        return AppError("无法连接模型服务", code=50262, status_code=502)
    return AppError(f"模型服务网络错误（{name}）", code=50266, status_code=502)
