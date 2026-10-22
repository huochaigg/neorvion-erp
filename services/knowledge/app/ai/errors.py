"""模型 HTTP 错误分类。摘要不得包含密钥。"""

from __future__ import annotations

import json
import re

import httpx

from app.core.exceptions import AppError

_SECRET = re.compile(r"(sk-[A-Za-z0-9._\-]+)|(Bearer\s+\S+)", re.IGNORECASE)


def redact_secrets(text: str) -> str:
    return _SECRET.sub("[redacted]", text)


def request_id_from_headers(headers: object | None) -> str | None:
    """只保留供应商请求追踪 ID，并去掉可能混入的密钥。"""
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    for key in ("x-request-id", "x-dashscope-request-id", "request-id", "x-requestid"):
        raw = getter(key)
        if not raw:
            continue
        cleaned = redact_secrets(str(raw)).strip()[:128]
        if cleaned and "sk-" not in cleaned.lower() and "bearer " not in cleaned.lower():
            return cleaned
    return None


def retry_after_seconds(headers: object | None) -> float | None:
    if headers is None or not hasattr(headers, "get"):
        return None
    raw = str(headers.get("retry-after") or "").strip()
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        return None
    if seconds < 0:
        return None
    return min(seconds, 120.0)


def classify_model_http_error(status: int, body: str, headers: object | None = None) -> AppError:
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

    trace = {
        "exception_type": "HTTPStatusError",
        "http_status": status,
        "request_id": request_id_from_headers(headers),
    }
    if status == 401 or "invalidapikey" in combined or "invalid api-key" in combined or "unauthorized" in combined:
        return AppError("模型服务认证失败，请检查密钥是否有效", code=40160, status_code=502, data=trace)
    if status == 403 or "permissiondenied" in combined or "access denied" in combined:
        return AppError("模型服务拒绝访问，请检查密钥权限或模型授权", code=40360, status_code=502, data=trace)
    if (
        status == 402
        or "arrearage" in combined
        or "insufficient" in combined
        or "balance" in combined
        or "quota exceeded" in combined
        or "exceeded your current quota" in combined
    ):
        return AppError("模型服务余额或配额不足，请充值或更换账号后再继续", code=40260, status_code=502, data=trace)
    if status == 429 or any(token in combined for token in ("rate_limit", "rate limit", "too many requests", "throttl")):
        data = {**trace, "retry_after_seconds": retry_after_seconds(headers)}
        return AppError("模型服务限流，请稍后从断点继续", code=42960, status_code=429, data=data)
    if any(
        token in combined
        for token in (
            "context_length",
            "context window",
            "maximum context",
            "too many tokens",
            "max_tokens",
            "token_limit",
        )
    ):
        return AppError(
            "单次请求超出模型上下文窗口，请缩短上下文或降低 Top-K，本题不会无限重试",
            code=40093,
            status_code=400,
        )
    if status in {408, 504}:
        return AppError(f"模型服务返回超时（HTTP {status}）", code=50460, status_code=504, data=trace)
    if status == 404:
        return AppError("模型接口地址不存在，请检查 Base URL 路径", code=40461, status_code=502, data=trace)
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
        return AppError(f"模型不存在或无权限：{detail}", code=40460, status_code=502, data=trace)
    if "dimension" in combined:
        return AppError("向量维度与配置不一致，请核对 Embedding 维度", code=40090, status_code=400, data=trace)
    if status >= 500:
        detail = f"：{safe_message}" if safe_message else ""
        return AppError(f"模型服务暂时不可用（HTTP {status}）{detail}", code=50260, status_code=502, data=trace)
    detail = safe_message or "请查看供应商返回的错误说明"
    return AppError(f"模型请求被拒绝（HTTP {status}）：{detail}", code=40094, status_code=400, data=trace)


def describe_model_transport(exc: httpx.HTTPError, *, service: str) -> AppError:
    """按 httpx 异常类型说明网络失败。50262 只表示未能再细分的连接或协议错误。"""
    name = type(exc).__name__
    text = str(exc).lower()
    data = {"exception_type": name, "http_status": None, "request_id": None}
    if isinstance(exc, httpx.ConnectTimeout):
        return AppError(
            f"连接{service}超时（{name}）。请检查网络或代理后从断点继续",
            code=50461,
            status_code=504,
            data=data,
        )
    if isinstance(exc, httpx.ReadTimeout):
        return AppError(
            f"等待{service}响应超时（{name}）。请求可能已到达供应商",
            code=50462,
            status_code=504,
            data=data,
        )
    if isinstance(exc, (httpx.WriteTimeout, httpx.PoolTimeout, httpx.TimeoutException)):
        return AppError(f"{service}超时（{name}）", code=50460, status_code=504, data=data)
    if isinstance(exc, httpx.ConnectError):
        if any(
            token in text
            for token in (
                "getaddrinfo",
                "name or service not known",
                "nodename nor servname",
                "temporary failure in name resolution",
            )
        ):
            return AppError(
                f"{service}域名无法解析（{name}）。请检查地址中的主机名或本机 DNS",
                code=50263,
                status_code=502,
                data=data,
            )
        if "connection refused" in text:
            return AppError(
                f"{service}端口拒绝连接（{name}）。请确认服务已启动且端口可访问",
                code=50265,
                status_code=502,
                data=data,
            )
        if any(token in text for token in ("certificate", "ssl", "tls")):
            return AppError(
                f"{service} TLS 握手失败（{name}）。请检查证书或 http/https 是否用错",
                code=50264,
                status_code=502,
                data=data,
            )
        # 50262：ConnectError 里没有 DNS、拒绝连接或 TLS 的明确信息。
        return AppError(
            f"无法建立到{service}的连接（{name}）。请检查网络连通性后从断点继续",
            code=50262,
            status_code=502,
            data=data,
        )
    if isinstance(exc, httpx.RemoteProtocolError):
        return AppError(f"{service}中断了响应（{name}）。可稍后从断点继续", code=50266, status_code=502, data=data)
    # 50262：其余非超时 httpx.HTTPError，调用方没有 HTTP 状态码。
    return AppError(f"{service}网络错误（{name}）。可稍后从断点继续", code=50262, status_code=502, data=data)


def describe_embedding_transport(exc: httpx.HTTPError) -> AppError:
    return describe_model_transport(exc, service="Embedding 服务")
