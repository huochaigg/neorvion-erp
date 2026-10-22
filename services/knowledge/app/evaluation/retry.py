"""模型调用的有限指数退避。上下文超限与密钥/余额错误不重试。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.ai.errors import redact_secrets
from app.core.config import settings
from app.core.exceptions import AppError
from app.evaluation.stages import (
    CONTEXT_OVERFLOW_CODES,
    PAUSE_RUN_CODES,
    RETRYABLE_CODES,
    InterruptReason,
    PauseRun,
    interrupt_code_reason,
)

logger = logging.getLogger(__name__)


def _exhausted_message(exc: AppError, attempts: int) -> str:
    """重试耗尽后的说明。只有读超时或 5xx 才提示请求可能已经产生费用。"""
    retries = max(attempts - 1, 0)
    if exc.code in {50460, 50462, 50260}:
        tail = "超时或服务端错误时，请求可能已产生费用。"
    elif exc.code == 42960:
        tail = "请稍后继续运行。"
    else:
        tail = "连接未完成时通常不会产生费用。"
    return f"{exc.message}；已尝试 {attempts} 次，重试 {retries} 次，可稍后继续运行。{tail}"


def interrupt_diagnostics(
    exc: AppError,
    *,
    stage: str | None,
    case_id: int | None,
    attempts: int,
) -> dict:
    """只保存脱敏诊断。不写入密钥、令牌或请求正文。"""
    data = exc.data if isinstance(exc.data, dict) else {}
    cause = exc.__cause__
    exception_type = str(data.get("exception_type") or (type(cause).__name__ if cause else "AppError"))
    request_id = data.get("request_id")
    safe_request_id = redact_secrets(str(request_id))[:128] if request_id else None
    return {
        "exception_type": redact_secrets(exception_type)[:80],
        "stage": stage,
        "case_id": case_id,
        "attempts": attempts,
        "retry_count": max(attempts - 1, 0),
        "last_error": redact_secrets(exc.message)[:500],
        "occurred_at": datetime.now(UTC).isoformat(),
        "request_id": safe_request_id,
        "http_status": data.get("http_status"),
        "error_code": exc.code,
    }


def _retry_delay(exc: AppError, fallback: float) -> float:
    if exc.code != 42960 or not isinstance(exc.data, dict):
        return fallback
    raw = exc.data.get("retry_after_seconds")
    if isinstance(raw, (int, float)) and raw >= 0:
        return min(float(raw), 120.0)
    return fallback


async def call_with_retry[T](
    factory: Callable[[], Awaitable[T]],
    *,
    what: str,
    stage: str | None = None,
    case_id: int | None = None,
) -> T:
    """对 429/超时/网络错误重试；上下文超限直接失败；密钥、拒绝访问与余额暂停 Run。"""
    attempts = max(1, int(getattr(settings, "eval_model_retries", 3)))
    delay = max(0.01, float(getattr(settings, "eval_retry_base_seconds", 0.2)))
    last_error: AppError | None = None
    for index in range(attempts):
        try:
            return await factory()
        except PauseRun:
            raise
        except AppError as exc:
            last_error = exc
            reason = interrupt_code_reason(exc)
            done = index + 1
            detail = interrupt_diagnostics(exc, stage=stage, case_id=case_id, attempts=done)
            if exc.code in CONTEXT_OVERFLOW_CODES:
                raise
            if exc.code in PAUSE_RUN_CODES:
                raise PauseRun(
                    reason or InterruptReason.MODEL_UNAVAILABLE.value,
                    exc.message,
                    diagnostics=detail,
                ) from exc
            cause_name = type(exc.__cause__).__name__ if exc.__cause__ is not None else "-"
            if exc.code in RETRYABLE_CODES and done < attempts:
                logger.warning(
                    "%s retry %s/%s code=%s cause=%s: %s",
                    what,
                    done,
                    attempts,
                    exc.code,
                    cause_name,
                    exc.message,
                )
                await asyncio.sleep(_retry_delay(exc, delay))
                delay *= 2
                continue
            if exc.code in RETRYABLE_CODES:
                logger.warning(
                    "%s exhausted code=%s cause=%s: %s",
                    what,
                    exc.code,
                    cause_name,
                    exc.message,
                    exc_info=exc.__cause__,
                )
                raise PauseRun(
                    reason or InterruptReason.NETWORK.value,
                    _exhausted_message(exc, attempts),
                    diagnostics=interrupt_diagnostics(exc, stage=stage, case_id=case_id, attempts=attempts),
                ) from exc
            raise
    assert last_error is not None
    raise last_error
