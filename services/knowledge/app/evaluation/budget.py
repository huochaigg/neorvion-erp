"""Run 级 Token / 费用预算。累计值以已落库 result.usage 为准，恢复时不从 0 重算。"""

from __future__ import annotations

from app.core.config import settings
from app.evaluation.stages import InterruptReason, PauseRun
from app.models.evaluation import EvaluationResult


def tokens_of(usage: dict | None) -> tuple[int, int, bool]:
    """返回 (prompt, completion, estimated)。缺精确值时用估算并打标。"""
    if not usage:
        return 0, 0, False
    estimated = bool(usage.get("token_estimated"))
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if prompt is None and completion is None:
        total = int(usage.get("estimated_tokens") or 0)
        return total, 0, True
    return int(prompt or 0), int(completion or 0), estimated


def cost_of(prompt_tokens: int, completion_tokens: int) -> float | None:
    prompt_rate = settings.eval_prompt_token_usd
    completion_rate = settings.eval_completion_token_usd
    if prompt_rate <= 0 and completion_rate <= 0:
        return None
    return (prompt_tokens / 1000) * prompt_rate + (completion_tokens / 1000) * completion_rate


def merge_embedding_usage(current: dict | None, incoming: dict | None) -> dict:
    """累计查询向量的真实调用和缓存命中。缓存命中不记成新的 API Token。"""
    base = dict(current or {})
    extra = incoming or {}
    base["embedding_api_calls"] = int(base.get("embedding_api_calls") or 0) + int(
        extra.get("embedding_api_calls") or 0
    )
    base["embedding_cache_hits"] = int(base.get("embedding_cache_hits") or 0) + int(
        extra.get("embedding_cache_hits") or 0
    )
    tokens = extra.get("embedding_prompt_tokens")
    if tokens is not None:
        base["embedding_prompt_tokens"] = int(base.get("embedding_prompt_tokens") or 0) + int(tokens)
    elif int(extra.get("embedding_api_calls") or 0) > 0:
        base["embedding_tokens_missing"] = True
    if extra.get("embedding_tokens_estimated"):
        base["embedding_tokens_estimated"] = True
    return base


def accumulate_results(rows: list[EvaluationResult]) -> dict:
    """从单题 usage 汇总 Run 用量，避免内存累加器在崩溃后丢失。"""
    prompt = 0
    completion = 0
    estimated = False
    latencies: list[int] = []
    completed = 0
    failed = 0
    embedding_api_calls = 0
    embedding_cache_hits = 0
    embedding_prompt_tokens = 0
    embedding_tokens_missing = False
    embedding_tokens_estimated = False
    for row in rows:
        usage = row.usage if isinstance(row.usage, dict) else None
        p, c, est = tokens_of(usage)
        prompt += p
        completion += c
        estimated = estimated or est
        latencies.append(int(row.latency_ms or 0))
        if usage:
            embedding_api_calls += int(usage.get("embedding_api_calls") or 0)
            embedding_cache_hits += int(usage.get("embedding_cache_hits") or 0)
            if usage.get("embedding_prompt_tokens") is not None:
                embedding_prompt_tokens += int(usage.get("embedding_prompt_tokens") or 0)
            embedding_tokens_missing = embedding_tokens_missing or bool(usage.get("embedding_tokens_missing"))
            embedding_tokens_estimated = embedding_tokens_estimated or bool(usage.get("embedding_tokens_estimated"))
        if row.result_status == "FAILED" or row.error_message:
            failed += 1
        elif row.result_status == "SUCCESS":
            completed += 1
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "token_estimated": estimated,
        "estimated_cost_usd": cost_of(prompt, completion),
        "embedding_api_calls": embedding_api_calls,
        "embedding_cache_hits": embedding_cache_hits,
        "embedding_prompt_tokens": embedding_prompt_tokens,
        "embedding_tokens_missing": embedding_tokens_missing,
        "embedding_tokens_estimated": embedding_tokens_estimated,
        "completed_count": completed,
        "failed_count": failed,
        "latencies": latencies,
    }


def estimate_next_call() -> int:
    """Provider 调用前的保守预留。不是精确值。"""
    return max(1, int(getattr(settings, "eval_token_reserve", 1500)))


def assert_budget(run, *, extra_tokens: int = 0, extra_cost: float = 0.0) -> None:
    """模型调用前检查剩余额度。耗尽时暂停，不把已完成题重跑。"""
    usage = run.usage if isinstance(run.usage, dict) else {}
    used_tokens = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
    budget = run.token_budget
    if budget is not None and used_tokens + extra_tokens > int(budget):
        raise PauseRun(InterruptReason.TOKEN_BUDGET.value, "Token 预算耗尽，请调高预算后继续运行")
    cost_budget = run.cost_budget_usd
    used_cost = usage.get("estimated_cost_usd")
    if cost_budget is not None and used_cost is not None and float(used_cost) + extra_cost > float(cost_budget):
        raise PauseRun(InterruptReason.COST_BUDGET.value, "费用预算耗尽，请调高预算后继续运行")
