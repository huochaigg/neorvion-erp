"""Event / OperationLog / Task 脱敏。禁止把密钥和认证信息写入审计表。"""

from __future__ import annotations

from typing import Any

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "encrypted_password",
        "temporary_password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "secret",
        "private_key",
        "api_key",
        "secret_key",
    }
)


def is_sensitive_key(key: str) -> bool:
    return key.lower() in _SENSITIVE_KEYS


def sanitize_payload(value: Any) -> Any:
    """递归去掉敏感键。只保留事件必要快照，不要序列化整个 ORM。"""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(str(key)):
                continue
            cleaned[str(key)] = sanitize_payload(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


def public_error_message(exc: BaseException) -> str:
    """给前端看的简要错误。不回传 traceback、绝对路径或 Token。"""
    from app.core.exceptions import AppError

    if isinstance(exc, AppError):
        return exc.message[:500]
    text = str(exc)
    lowered = text.lower()
    if "password" in lowered or "token" in lowered or "secret" in lowered:
        return "任务执行失败，请查看任务日志"
    if ":\\" in text or text.startswith("/") or "Traceback" in text:
        return "任务执行失败，请稍后重试"
    return text[:500]
