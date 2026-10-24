"""R2-08：上下文遗漏、预算、引用映射。不调用外部模型。"""

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.context_pack import pack_retrieved_hits, prompt_observability
from app.evaluation.prompt import build_rag_messages, format_evidence_block, pack_prompt_hits
from app.services.retrieval import RetrievedHit

_CHUNK_DUMP = Path(__file__).resolve().parents[1] / "eval_fixtures" / "v8-round2" / "_chunk_dump.json"


def _legacy_select(hits: list[RetrievedHit], budget: int) -> tuple[list[int], int]:
    selected: list[RetrievedHit] = []
    used = 0
    for index, hit in enumerate(hits, start=1):
        block = format_evidence_block(index, hit)
        if used + len(block) > budget:
            break
        selected.append(hit)
        used += len(block)
    return [item.chunk_id for item in selected], used


def _load_chunks() -> dict[int, dict]:
    rows = json.loads(_CHUNK_DUMP.read_text(encoding="utf-8"))
    return {int(item["id"]): item for item in rows}


def _hits(ids: list[int], chunks: dict[int, dict]) -> list[RetrievedHit]:
    hits: list[RetrievedHit] = []
    for rank, chunk_id in enumerate(ids, start=1):
        item = chunks[chunk_id]
        hits.append(
            RetrievedHit(
                chunk_id=chunk_id,
                document_id=int(item["document_id"]),
                knowledge_base_id=8,
                filename=str(item["filename"]),
                content=str(item["content"]),
                page_no=1,
                heading=item.get("heading"),
                chunk_index=int(item.get("chunk_index") or 0),
                version=1,
                final_rank=rank,
            )
        )
    return hits


def test_run53_case249_prompt_includes_tail_document() -> None:
    chunks = _load_chunks()
    hits = _hits([89, 124, 102, 128, 101, 129, 81, 77], chunks)
    old_ids, old_used = _legacy_select(hits, 6000)
    packed = pack_prompt_hits(hits, budget=6000)
    assert 77 not in old_ids
    assert 77 not in packed.prompt_ids
    assert packed.omitted_reasons.get(77) == "budget"
    assert packed.used_chars <= 6000
    assert packed.partially_truncated_chunk_count == 0
    assert packed.context_budget_limited is True
    print(
        "case249",
        {"old": old_ids, "new": packed.prompt_ids, "old_used": old_used, "new_used": packed.used_chars},
    )


def test_run53_case339_packing_report() -> None:
    chunks = _load_chunks()
    hits = _hits([85, 72, 71, 65, 128, 126, 101, 64], chunks)
    old_ids, old_used = _legacy_select(hits, 6000)
    packed = pack_prompt_hits(hits, budget=6000)
    assert 64 not in old_ids
    assert packed.used_chars <= 6000
    print(
        "case339",
        {
            "old": old_ids,
            "new": packed.prompt_ids,
            "gold64_in_new": 64 in packed.prompt_ids,
            "old_used": old_used,
            "new_used": packed.used_chars,
        },
    )


def test_citation_mapping_keeps_original_chunk_ids() -> None:
    chunks = _load_chunks()
    hits = _hits([89, 124, 77], chunks)
    trace = build_rag_messages("采购退货 WAITING_OUTBOUND 是什么？", hits, budget=6000)
    blob = trace.messages[1]["content"]
    for index, chunk_id in enumerate(trace.prompt_chunk_ids, start=1):
        assert f"[{index}]" in blob
        assert f"chunk_id={chunk_id}" in blob
    assert "expected_answer" not in blob
    assert "<gold>" not in blob


def test_pack_retrieved_hits_records_omitted_reason() -> None:
    chunks = _load_chunks()
    hits = _hits([89, 124, 102, 128, 101, 129, 81, 77], chunks)
    rows = pack_retrieved_hits(hits, {"judgments": []}, context_budget=6000)
    omitted = [item for item in rows if item["in_prompt"] is False]
    assert omitted
    assert all(item["omitted_reason"] in {"budget", "duplicate", "empty", "other"} for item in omitted)
    assert all(item["partially_truncated"] is False for item in rows)
    stats = prompt_observability(rows)
    assert stats["context_budget_limited"] is True
    assert stats["budget_limit_chars"] == 6000
    assert stats["omitted_chunk_count"] == len(omitted)
    assert 77 in stats["omitted_chunk_ids"]
