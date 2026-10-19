"""模型调用的有限指数退避。上下文超限与密钥/余额错误不重试。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

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


async def call_with_retry[T](factory: Callable[[], Awaitable[T]], *, what: str) -> T:
    """对 429/超时/网络错误重试；上下文超限直接失败；密钥与余额暂停 Run。"""
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
            if exc.code in CONTEXT_OVERFLOW_CODES:
                raise
            if exc.code in PAUSE_RUN_CODES:
                raise PauseRun(reason or InterruptReason.MODEL_UNAVAILABLE.value, exc.message) from exc
            if exc.code in RETRYABLE_CODES and index + 1 < attempts:
                logger.warning("%s retry %s/%s: %s", what, index + 1, attempts, exc.message)
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if exc.code in RETRYABLE_CODES:
                raise PauseRun(
                    reason or InterruptReason.RATE_LIMIT.value,
                    f"{exc.message}；已达最大重试次数，可稍后继续运行。超时请求可能已产生费用。",
                ) from exc
            raise
    assert last_error is not None
    raise last_error
