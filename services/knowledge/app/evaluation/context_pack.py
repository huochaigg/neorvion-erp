"""评测命中的展示摘要与生成上下文分离。

线上 Chat 按 chat_max_context_chars 顺序截断完整切片。
评测如果把每条 content 先切成 500 字再拿去生成和 Judge，会和线上问答不一致。
这里仍只持久化有界摘录，不保存整篇文档。
"""

from __future__ import annotations

DISPLAY_SNIPPET_CHARS = 500
_MAX_CANDIDATES = 48


def generation_text(item: dict) -> str:
    """生成和 Judge 使用的摘录。旧结果没有该字段时退回展示摘要。"""
    if "generation_excerpt" in item:
        return str(item.get("generation_excerpt") or "")
    return str(item.get("content") or "")


def pack_retrieved_hits(hits, case: dict, *, context_budget: int) -> list[dict]:
    """按最终排名分配生成摘录预算，展示字段固定为前 500 字。

    context_budget 与 Chat 的总上下文字符预算对齐，按命中顺序消耗。
    预算用尽后后续命中的 generation_excerpt 为空，并标记 generation_truncated。
    """
    label_map = {
        int(item["chunk_id"]): int(item["relevance"])
        for item in case.get("judgments") or []
        if not item.get("stale")
    }
    remaining = max(0, int(context_budget))
    packed: list[dict] = []
    for hit in hits:
        full = str(getattr(hit, "content", "") or "")
        take = min(len(full), remaining)
        excerpt = full[:take]
        remaining -= take
        packed.append(
            {
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "filename": hit.filename,
                "content": full[:DISPLAY_SNIPPET_CHARS],
                "generation_excerpt": excerpt,
                "content_chars": len(full),
                "generation_truncated": take < len(full),
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
    return packed


def retrieval_diagnostics(search, *, context_budget: int, packed: list[dict]) -> dict:
    """只保留候选 ID、名次和分数，不重复保存正文。"""
    stages = search.stages if isinstance(getattr(search, "stages", None), dict) else {}
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
        "vector_ranks": _trim_ranks(stages.get("vector_ranks"), "similarity"),
        "keyword_ranks": _trim_ranks(stages.get("keyword_ranks"), "score"),
        "rrf_ranks": _trim_ranks(stages.get("rrf_ranks"), "rrf"),
        "final_chunk_ids": [item.get("chunk_id") for item in packed],
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
