"""模型 HTTP 错误分类。摘要不得包含密钥。"""

from __future__ import annotations

import json
import re

from app.core.exceptions import AppError

_SECRET = re.compile(r"(sk-[A-Za-z0-9._\-]+)|(Bearer\s+\S+)", re.IGNORECASE)


def redact_secrets(text: str) -> str:
    return _SECRET.sub("[redacted]", text)


def classify_model_http_error(status: int, body: str) -> AppError:
    """把供应商错误映射成可读原因：密钥、余额、模型不存在、地址错误等。"""
    raw = redact_secrets(body or "")
    code_name = ""
    message = ""
    try:
        payload = json.loads(body or "")
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        raw_error = payload.get("error")
        error = raw_error if isinstance(raw_error, dict) else {}
        code_name = str(payload.get("code") or error.get("code") or error.get("type") or "")
        message = str(payload.get("message") or error.get("message") or "")
    combined = f"{code_name} {message} {raw}".lower()
    safe_message = redact_secrets(message).strip()[:180]

    if status == 401 or "invalidapikey" in combined or "invalid api-key" in combined or "unauthorized" in combined:
        return AppError("模型服务认证失败，请检查密钥配置", code=40160, status_code=502)
    if (
        status == 402
        or "arrearage" in combined
        or "insufficient" in combined
        or "balance" in combined
        or "quota exceeded" in combined
        or "exceeded your current quota" in combined
    ):
        return AppError("模型服务余额不足", code=40260, status_code=502)
    if status == 429:
        return AppError("模型服务限流，请稍后重试", code=42960, status_code=429)
    if status in {408, 504}:
        return AppError("模型服务超时", code=50460, status_code=504)
    if status == 404:
        return AppError("模型接口地址不存在，请检查 Base URL", code=40461, status_code=502)
    if any(
        token in combined
        for token in (
            "model_not_found",
            "model not exist",
            "model not found",
            "unknown model",
            "does not exist",
            "invalid_model",
        )
    ):
        detail = safe_message or "请检查模型 ID 或工作空间权限"
        return AppError(f"模型不存在或无权限：{detail}", code=40460, status_code=502)
    if "dimension" in combined:
        return AppError("向量维度与配置不一致", code=40090, status_code=400)
    if safe_message:
        return AppError(f"模型服务错误（{status}）：{safe_message}", code=50260, status_code=502)
    snippet = raw[:200]
    return AppError(f"模型服务错误（{status}）", code=50260, status_code=502, data={"detail": snippet})
