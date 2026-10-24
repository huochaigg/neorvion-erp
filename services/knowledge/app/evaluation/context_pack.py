"""评测命中的展示摘要与生成上下文分离。

线上 Chat 与评测打包共用 pack_prompt_hits：整段纳入或整段丢弃。
这里仍只持久化有界摘录，不保存整篇文档。
"""

from __future__ import annotations

from app.core.config import settings
from app.evaluation.prompt import pack_prompt_hits

DISPLAY_SNIPPET_CHARS = 500
_MAX_CANDIDATES = 48


def generation_text(item: dict) -> str:
    """生成和 Judge 使用的摘录。旧结果没有该字段时退回展示摘要。"""
    if "generation_excerpt" in item:
        return str(item.get("generation_excerpt") or "")
    return str(item.get("content") or "")


def pack_retrieved_hits(hits, case: dict, *, context_budget: int) -> list[dict]:
    """展示字段固定为前 500 字；生成摘录与 Chat 相同：整段纳入或整段丢弃。"""
    label_map = {
        int(item["chunk_id"]): int(item["relevance"])
        for item in case.get("judgments") or []
        if not item.get("stale")
    }
    packed_prompt = pack_prompt_hits(list(hits), budget=int(context_budget))
    selected_ids = {int(getattr(item, "chunk_id")) for item in packed_prompt.selected}
    rows: list[dict] = []
    for hit in hits:
        full = str(getattr(hit, "content", "") or "")
        chunk_id = int(hit.chunk_id)
        in_prompt = chunk_id in selected_ids
        omitted_reason = None if in_prompt else packed_prompt.omitted_reasons.get(chunk_id)
        if omitted_reason is None and not in_prompt:
            omitted_reason = "empty" if not full.strip() else "budget"
        rows.append(
            {
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "filename": hit.filename,
                "content": full[:DISPLAY_SNIPPET_CHARS],
                "generation_excerpt": full if in_prompt else "",
                "content_chars": len(full),
                "in_prompt": in_prompt,
                "generation_truncated": not in_prompt,
                "omitted_reason": omitted_reason,
                "partially_truncated": False,
                "page_no": getattr(hit, "page_no", None),
                "heading": getattr(hit, "heading", None),
                "version": getattr(hit, "version", None),
                "final_rank": hit.final_rank,
                "vector_score": hit.vector_score,
                "keyword_score": hit.keyword_score,
                "rrf_score": hit.rrf_score,
                "rerank_score": hit.rerank_score,
                "vector_rank": getattr(hit, "vector_rank", None),
                "keyword_rank": getattr(hit, "keyword_rank", None),
                "relevance": label_map.get(hit.chunk_id),
            }
        )
    return rows


def retrieval_diagnostics(search, *, context_budget: int, packed: list[dict]) -> dict:
    """只保留候选 ID、名次和分数，不重复保存正文。"""
    stages = search.stages if isinstance(getattr(search, "stages", None), dict) else {}
    observability = prompt_observability(packed, trace=None, context_budget=context_budget)
    return {
        "rerank_applied": bool(getattr(search, "rerank_applied", False)),
        "rerank_degraded": bool(getattr(search, "rerank_degraded", False)),
        "rerank_ms": stages.get("rerank_ms"),
        "vector_ms": stages.get("vector_ms"),
        "keyword_ms": stages.get("keyword_ms"),
        "embedding_cache_hit": bool(stages.get("embedding_cache_hit")),
        "embedding_api_calls": int(stages.get("embedding_api_calls") or 0),
        "embedding_cache_hits": int(stages.get("embedding_cache_hits") or 0),
        "embedding_prompt_tokens": stages.get("embedding_prompt_tokens"),
        "context_budget_chars": int(context_budget),
        "generation_truncated_count": sum(1 for item in packed if item.get("generation_truncated")),
        "prompt_chunk_ids": observability["prompt_chunk_ids"],
        "retrieved_chunk_ids": observability["retrieved_chunk_ids"],
        "omitted_chunk_ids": observability["omitted_chunk_ids"],
        "omitted_chunk_count": observability["omitted_chunk_count"],
        "partially_truncated_chunk_count": observability["partially_truncated_chunk_count"],
        "prompt_truncated": observability["prompt_truncated"],
        "context_budget_limited": observability["context_budget_limited"],
        "truncation_reason": observability["truncation_reason"],
        "budget_used_chars": observability["budget_used_chars"],
        "budget_limit_chars": observability["budget_limit_chars"],
        "vector_ranks": _trim_ranks(stages.get("vector_ranks"), "similarity"),
        "keyword_ranks": _trim_ranks(stages.get("keyword_ranks"), "score"),
        "rrf_ranks": _trim_ranks(stages.get("rrf_ranks"), "rrf"),
        "final_chunk_ids": [item.get("chunk_id") for item in packed],
    }


def prompt_observability(retrieved: list[dict] | None, trace=None, *, context_budget: int | None = None) -> dict:
    """从打包结果还原截断统计。不依赖 GENERATE 是否把已过滤列表再送进 Context Builder。"""
    rows = [item for item in (retrieved or []) if isinstance(item, dict) and item.get("chunk_id") is not None]
    retrieved_ids = [int(item["chunk_id"]) for item in rows]
    has_flags = any("in_prompt" in item for item in rows)
    if has_flags:
        prompt_ids = [int(item["chunk_id"]) for item in rows if item.get("in_prompt") is True]
        omitted_rows = [item for item in rows if item.get("in_prompt") is False]
    elif trace is not None:
        prompt_ids = list(getattr(trace, "prompt_chunk_ids", None) or [])
        prompt_set = set(prompt_ids)
        omitted_rows = [item for item in rows if int(item["chunk_id"]) not in prompt_set]
    else:
        prompt_ids = [int(item["chunk_id"]) for item in rows if generation_text(item)]
        prompt_set = set(prompt_ids)
        omitted_rows = [item for item in rows if int(item["chunk_id"]) not in prompt_set]

    omitted_ids = [int(item["chunk_id"]) for item in omitted_rows]
    reasons: list[str] = []
    for item in omitted_rows:
        reason = item.get("omitted_reason")
        if reason not in {"budget", "empty", "duplicate", "other"}:
            excerpt = generation_text(item) if "generation_excerpt" in item else str(item.get("content") or "")
            chars = int(item.get("content_chars") or len(str(item.get("content") or "")))
            reason = "empty" if chars == 0 or not str(excerpt or item.get("content") or "").strip() else "budget"
        reasons.append(str(reason))

    truncation_reason = None
    if any(item == "budget" for item in reasons):
        truncation_reason = "budget"
    elif reasons and all(item == "empty" for item in reasons):
        truncation_reason = "empty"
    elif omitted_ids:
        truncation_reason = "other"

    budget_limit = (
        int(getattr(trace, "budget_chars", 0) or 0)
        or int(context_budget or 0)
        or int(settings.chat_max_context_chars)
    )
    if trace is not None and getattr(trace, "used_chars", None) is not None:
        budget_used = int(trace.used_chars)
    else:
        budget_used = sum(int(item.get("content_chars") or len(generation_text(item))) for item in rows if item.get("in_prompt") is True)

    context_budget_limited = truncation_reason == "budget"
    return {
        "retrieved_chunk_ids": retrieved_ids,
        "prompt_chunk_ids": prompt_ids,
        "omitted_chunk_ids": omitted_ids,
        "omitted_chunk_count": len(omitted_ids),
        "partially_truncated_chunk_count": sum(1 for item in rows if item.get("partially_truncated")),
        "truncation_reason": truncation_reason,
        "context_budget_limited": context_budget_limited,
        "prompt_truncated": context_budget_limited,
        "budget_used_chars": budget_used,
        "budget_limit_chars": budget_limit,
    }


def _trim_ranks(rows, score_key: str) -> list[dict]:
    if not isinstance(rows, list):
        return []
    trimmed = []
    for item in rows[:_MAX_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        trimmed.append(
            {
                "chunk_id": item.get("chunk_id"),
                "rank": item.get("rank"),
                score_key: item.get(score_key if score_key in item else "rrf"),
            }
        )
    return trimmed
