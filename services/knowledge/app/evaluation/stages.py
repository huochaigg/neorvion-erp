"""评测阶段与中断原因。阶段名与当前执行器一致：检索一次完成 RETRIEVE+RERANK。"""

from __future__ import annotations

from enum import StrEnum

from app.core.exceptions import AppError


class EvalStage(StrEnum):
    RETRIEVE = "RETRIEVE"
    RERANK = "RERANK"
    GENERATE = "GENERATE"
    JUDGE = "JUDGE"
    METRICS = "METRICS"


class StageStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"


class ResultCaseStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class InterruptReason(StrEnum):
    USER_PAUSE = "USER_PAUSE"
    TOKEN_BUDGET = "TOKEN_BUDGET"
    COST_BUDGET = "COST_BUDGET"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    INVALID_KEY = "INVALID_KEY"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    CASE_FAILED = "CASE_FAILED"
    WORKER_CRASH = "WORKER_CRASH"
    SNAPSHOT_UNAVAILABLE = "SNAPSHOT_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    CANCELLED = "CANCELLED"


INTERRUPT_LABEL = {
    InterruptReason.USER_PAUSE.value: "用户暂停",
    InterruptReason.TOKEN_BUDGET.value: "Token 预算耗尽",
    InterruptReason.COST_BUDGET.value: "费用预算耗尽",
    InterruptReason.RATE_LIMIT.value: "模型限流",
    InterruptReason.TIMEOUT.value: "模型超时",
    InterruptReason.INSUFFICIENT_FUNDS.value: "模型余额不足",
    InterruptReason.INVALID_KEY.value: "模型密钥无效",
    InterruptReason.CONTEXT_OVERFLOW.value: "单次上下文超限",
    InterruptReason.CASE_FAILED.value: "单题执行失败",
    InterruptReason.WORKER_CRASH.value: "Worker 异常退出",
    InterruptReason.SNAPSHOT_UNAVAILABLE.value: "原始快照或索引不可用",
    InterruptReason.MODEL_UNAVAILABLE.value: "快照中的模型配置不可用",
    InterruptReason.CANCELLED.value: "已取消",
}

# 限流 / 超时 / 短暂网络：有限重试。余额、密钥、上下文超限：不重试。
RETRYABLE_CODES = {42960, 50460, 50262, 50260, 50201, 50202}
PAUSE_RUN_CODES = {40160, 40260, 50360, 50361, 50362}
CONTEXT_OVERFLOW_CODES = {40093}


class PauseRun(Exception):
    """中断整次 Run 并保留已落库结果，等待用户或 Worker 恢复。"""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def empty_stages() -> dict:
    return {
        item.value: {"status": StageStatus.PENDING.value, "latency_ms": 0, "usage": None, "error": None}
        for item in EvalStage
    }


def stage_entry(stages: dict | None, name: str) -> dict:
    payload = stages if isinstance(stages, dict) else {}
    item = payload.get(name)
    return item if isinstance(item, dict) else {}


def stage_status(stages: dict | None, name: str) -> str:
    return str(stage_entry(stages, name).get("status") or StageStatus.PENDING.value)


def mark_stage(
    stages: dict | None,
    name: str,
    status: str,
    *,
    latency_ms: int = 0,
    usage: dict | None = None,
    error: str | None = None,
) -> dict:
    payload = dict(stages) if isinstance(stages, dict) else empty_stages()
    current = dict(stage_entry(payload, name))
    current["status"] = status
    current["latency_ms"] = latency_ms
    if usage is not None:
        current["usage"] = usage
    current["error"] = error
    payload[name] = current
    return payload


def stage_succeeded(status: str) -> bool:
    return status in {StageStatus.SUCCESS.value, StageStatus.SKIPPED.value, StageStatus.DEGRADED.value}


def interrupt_code_reason(exc: AppError) -> str | None:
    if exc.code in CONTEXT_OVERFLOW_CODES:
        return InterruptReason.CONTEXT_OVERFLOW.value
    if exc.code == 42960:
        return InterruptReason.RATE_LIMIT.value
    if exc.code == 50460:
        return InterruptReason.TIMEOUT.value
    if exc.code == 40260:
        return InterruptReason.INSUFFICIENT_FUNDS.value
    if exc.code in {40160, 50360, 50361, 50362}:
        return InterruptReason.INVALID_KEY.value
    return None
