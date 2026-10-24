"""引用验证：只检查回答里的 [n] 能否追溯到 Prompt 中的 Chunk。

引用数量不是正确率。没有 [n] 时 citation_correctness 为 null，不能记成 0 或 1。
三个独立维度：
1. citation_validity：编号合法且指向本次 Prompt。
2. gold_citation_match：引用是否命中 primary 或 alternative；不能当作真实引用正确率。
3. claim_support：引用是否支持回答中的具体主张。当前没有可靠实现，保持未评测。
历史字段 citation_correctness 保留，避免破坏旧 Run；其值等于 gold 命中率。
"""

from __future__ import annotations

import re

CITATION_METRIC_VERSION = "v2-validity-gold-claim"
_CITATION = re.compile(r"\[(\d{1,3})\]")


def parse_cited_ranks(answer: str | None) -> list[int]:
    seen: list[int] = []
    for raw in _CITATION.findall(answer or ""):
        rank = int(raw)
        if rank not in seen:
            seen.append(rank)
    return seen


def citation_metrics(
    answer: str | None,
    prompt_chunk_ids: list[int],
    *,
    gold_chunk_ids: list[int] | None = None,
    support_chunk_ids: list[int] | None = None,
    is_unanswerable: bool = False,
) -> dict:
    """确定性引用检查。prompt_chunk_ids 的顺序必须与 Prompt 中 [1]、[2] 一致。"""
    cited_ranks = parse_cited_ranks(answer)
    prompt_ids = [int(item) for item in prompt_chunk_ids]
    size = len(prompt_ids)
    mapped: list[dict] = []
    invalid_ranks: list[int] = []
    cited_chunk_ids: list[int] = []
    for rank in cited_ranks:
        if rank < 1 or rank > size:
            invalid_ranks.append(rank)
            mapped.append({"rank": rank, "chunk_id": None, "in_prompt": False})
            continue
        chunk_id = prompt_ids[rank - 1]
        cited_chunk_ids.append(chunk_id)
        mapped.append({"rank": rank, "chunk_id": chunk_id, "in_prompt": True})

    gold = {int(item) for item in gold_chunk_ids or [] if item is not None}
    support = {int(item) for item in (support_chunk_ids or list(gold)) if item is not None}
    supported_ids = [cid for cid in cited_chunk_ids if cid in support]
    gold_ids = [cid for cid in cited_chunk_ids if cid in gold]
    valid_count = len(cited_ranks) - len(invalid_ranks)

    if not cited_ranks:
        status = "no_explicit_citation"
        index_precision = None
        support_rate = None
        correctness = None
        skipped = "no_explicit_citation"
    else:
        skipped = None
        index_precision = valid_count / len(cited_ranks)
        support_rate = (len(supported_ids) / len(cited_chunk_ids)) if cited_chunk_ids else 0.0
        if is_unanswerable:
            status = "unanswerable_with_citation"
            correctness = None
            skipped = "unanswerable"
        else:
            status = "invalid_rank" if invalid_ranks and valid_count == 0 else (
                "mixed" if invalid_ranks else "valid_index"
            )
            if not cited_chunk_ids:
                correctness = 0.0
            elif support:
                correctness = len(supported_ids) / len(cited_ranks)
            else:
                correctness = None
                skipped = "no_gold_or_fact_chunks"

    return {
        "citation_metric_version": CITATION_METRIC_VERSION,
        "cited_ranks": cited_ranks,
        "cited_chunk_ids": cited_chunk_ids,
        "invalid_ranks": invalid_ranks,
        "prompt_chunk_ids": prompt_ids,
        "prompt_count": size,
        "mapped": mapped,
        "status": status,
        "citation_index_precision": index_precision,
        "citation_supported_chunk_ids": supported_ids,
        "citation_gold_chunk_ids": gold_ids,
        "citation_supported_rate": support_rate,
        "citation_correctness": correctness,
        "citation_correctness_skipped": skipped,
        "citation_validity": index_precision,
        "citation_validity_skipped": None if cited_ranks else skipped,
        "gold_citation_match": correctness,
        "gold_citation_match_skipped": skipped,
        "claim_support": None,
        "claim_support_skipped": "not_evaluated",
        "note": (
            "citation_correctness 是历史兼容字段，等于 gold_citation_match，不是真实引用正确率。"
            "citation_validity 只检查 [n] 是否落在本次 Prompt。"
            "gold_citation_match 只检查是否命中 primary/alternative。"
            "claim_support 当前未评测。"
            "没有 [n] 时上述比例为 null。"
        ),
    }
