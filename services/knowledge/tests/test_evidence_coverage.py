"""Evidence Coverage 与 Chunk Recall 独立；禁止把 alternative 跨事实合并。"""

from __future__ import annotations

import pytest

from app.evaluation.evidence import (
    LiveChunk,
    classify_evidence_chunks,
    evidence_coverage_metrics,
    parse_case_evidence,
)
from app.evaluation.metrics import (
    LabeledItem,
    aggregate_retrieval,
    retrieval_metrics,
    unanswerable_retrieval_stats,
)

CASE_257 = {
    "id": 257,
    "is_unanswerable": False,
    "tags": [
        "required_facts:draft-vs-counting",
        "fact:draft-vs-counting=139",
        "primary:draft-vs-counting=139",
        "alt:draft-vs-counting=138",
    ],
    "judgments": [{"chunk_id": 139, "relevance": 3, "stale": False, "document_id": 45}],
}

CASE_259 = {
    "id": 259,
    "is_unanswerable": False,
    "tags": [
        "required_facts:two-refunds|refund-no-stock",
        "primary:two-refunds=102",
        "primary:refund-no-stock=82",
        "partial:refund-no-stock=78",
    ],
    "judgments": [
        {"chunk_id": 82, "relevance": 3, "stale": False, "document_id": 39},
        {"chunk_id": 102, "relevance": 2, "stale": False, "document_id": 41},
    ],
}


def _live(*ids: int, kb: int = 8, tenant: int = 3, status: str = "ACTIVE", enabled: bool = True) -> dict[int, LiveChunk]:
    return {
        cid: LiveChunk(
            chunk_id=cid,
            tenant_id=tenant,
            knowledge_base_id=kb,
            status=status,
            enabled=enabled,
        )
        for cid in ids
    }


def _valid(case: dict, live: dict[int, LiveChunk]) -> tuple:
    spec = parse_case_evidence(case)
    assert spec is not None
    return classify_evidence_chunks(
        spec,
        judgments=list(case.get("judgments") or []),
        live_chunks=live,
        allowed_kb_ids={8},
        tenant_id=3,
    )


def _coverage(case: dict, ranked: list[int], k: int, live_ids: tuple[int, ...]):
    spec = parse_case_evidence(case)
    valid, rejected = _valid(case, _live(*live_ids))
    return evidence_coverage_metrics(ranked, spec, k=k, valid_chunk_ids=valid, rejected=rejected)


def test_parse_v4_tags_keeps_primary_alt_partial_separate() -> None:
    spec_257 = parse_case_evidence(CASE_257)
    assert spec_257 is not None
    assert spec_257.required_fact_ids == ("draft-vs-counting",)
    fact = spec_257.fact("draft-vs-counting")
    assert fact is not None
    assert fact.primary_chunk_ids == (139,)
    assert fact.alternative_chunk_ids == (138,)

    spec_259 = parse_case_evidence(CASE_259)
    assert spec_259 is not None
    assert spec_259.required_fact_ids == ("two-refunds", "refund-no-stock")
    refund = spec_259.fact("refund-no-stock")
    assert refund is not None
    assert refund.primary_chunk_ids == (82,)
    assert refund.partial_chunk_ids == (78,)
    assert 78 not in refund.alternative_chunk_ids


def test_primary_hit_covers_fact() -> None:
    row = _coverage(CASE_257, [139, 10], k=8, live_ids=(139, 138))
    assert row["evidence_coverage_at_k"] == 1.0
    assert row["complete_evidence_at_k"] is True
    assert row["facts"][0]["hit_role"] == "primary"
    assert row["facts"][0]["hit_chunk_ids"] == [139]


def test_alternative_hit_covers_same_fact() -> None:
    row = _coverage(CASE_257, [138], k=8, live_ids=(139, 138))
    assert row["evidence_coverage_at_k"] == 1.0
    assert row["complete_evidence_at_k"] is True
    assert row["facts"][0]["hit_role"] == "alternative"
    assert row["facts"][0]["hit_chunk_ids"] == [138]


def test_neither_primary_nor_alternative_is_zero() -> None:
    row = _coverage(CASE_257, [99, 100], k=8, live_ids=(139, 138))
    assert row["evidence_coverage_at_k"] == 0.0
    assert row["complete_evidence_at_k"] is False
    assert row["uncovered_facts"] == ["draft-vs-counting"]


def test_multi_fact_partial_hit_is_half() -> None:
    row = _coverage(CASE_259, [102], k=8, live_ids=(82, 102, 78))
    assert row["evidence_coverage_at_k"] == pytest.approx(0.5)
    assert row["complete_evidence_at_k"] is False
    assert row["uncovered_facts"] == ["refund-no-stock"]
    by_id = {item["fact_id"]: item for item in row["facts"]}
    assert by_id["two-refunds"]["covered"] is True
    assert by_id["refund-no-stock"]["covered"] is False


def test_multi_fact_all_hit_is_complete() -> None:
    row = _coverage(CASE_259, [82, 102], k=8, live_ids=(82, 102, 78))
    assert row["evidence_coverage_at_k"] == 1.0
    assert row["complete_evidence_at_k"] is True
    assert row["uncovered_facts"] == []


def test_one_chunk_can_cover_multiple_facts() -> None:
    case = {
        "tags": [
            "required_facts:high-risk|read-snapshot",
            "primary:high-risk=111",
            "primary:read-snapshot=111",
            "alt:high-risk=112",
            "alt:read-snapshot=112",
        ],
        "judgments": [{"chunk_id": 111, "relevance": 3, "stale": False}],
    }
    row = _coverage(case, [111], k=8, live_ids=(111, 112))
    assert row["covered_fact_count"] == 2
    assert row["complete_evidence_at_k"] is True
    assert {item["hit_role"] for item in row["facts"]} == {"primary"}


def test_partial_cannot_cover_fact_alone() -> None:
    row = _coverage(CASE_259, [78], k=8, live_ids=(82, 102, 78))
    assert row["evidence_coverage_at_k"] == 0.0
    assert row["complete_evidence_at_k"] is False
    refund = next(item for item in row["facts"] if item["fact_id"] == "refund-no-stock")
    assert refund["covered"] is False
    assert refund["partial_hit_chunk_ids"] == [78]


def test_unanswerable_skips_coverage() -> None:
    stats = unanswerable_retrieval_stats([1, 2], k=8)
    coverage = evidence_coverage_metrics(
        [1, 2],
        parse_case_evidence(CASE_257),
        k=8,
        valid_chunk_ids={139},
        is_unanswerable=True,
    )
    assert "recall" not in stats
    assert coverage["evidence_coverage_skipped"] == "unanswerable"
    assert "evidence_coverage_at_k" not in coverage


def test_stale_missing_and_wrong_kb_are_rejected() -> None:
    spec = parse_case_evidence(CASE_257)
    assert spec is not None
    valid, rejected = classify_evidence_chunks(
        spec,
        judgments=[{"chunk_id": 139, "stale": True}],
        live_chunks={
            **_live(138, kb=9),
        },
        allowed_kb_ids={8},
        tenant_id=3,
    )
    assert 139 not in valid
    assert rejected[139] == "stale"
    assert rejected[138] == "wrong_kb"

    missing_valid, missing_rejected = classify_evidence_chunks(
        spec,
        judgments=[],
        live_chunks={},
        allowed_kb_ids={8},
        tenant_id=3,
    )
    assert missing_valid == set()
    assert missing_rejected[139] == "missing"
    unevaluable = evidence_coverage_metrics(
        [139],
        spec,
        k=8,
        valid_chunk_ids=missing_valid,
        rejected=missing_rejected,
    )
    assert unevaluable["evidence_coverage_skipped"] == "unevaluable_evidence"
    assert "evidence_coverage_at_k" not in unevaluable


def test_same_question_different_top_k() -> None:
    live_ids = (82, 102, 78)
    at_1 = _coverage(CASE_259, [102, 82], k=1, live_ids=live_ids)
    at_2 = _coverage(CASE_259, [102, 82], k=2, live_ids=live_ids)
    assert at_1["evidence_coverage_at_k"] == pytest.approx(0.5)
    assert at_1["complete_evidence_at_k"] is False
    assert at_2["evidence_coverage_at_k"] == 1.0
    assert at_2["complete_evidence_at_k"] is True


def test_cannot_merge_alternatives_across_facts() -> None:
    case = {
        "tags": [
            "required_facts:a|b",
            "primary:a=1",
            "primary:b=2",
            "alt:a=99",
        ],
        "judgments": [
            {"chunk_id": 1, "relevance": 2, "stale": False},
            {"chunk_id": 2, "relevance": 2, "stale": False},
        ],
    }
    row = _coverage(case, [99], k=8, live_ids=(1, 2, 99))
    assert row["evidence_coverage_at_k"] == pytest.approx(0.5)
    assert row["complete_evidence_at_k"] is False
    assert row["uncovered_facts"] == ["b"]


def test_answerable_without_required_facts_is_not_coverage_one() -> None:
    row = evidence_coverage_metrics([10], None, k=8, valid_chunk_ids={10})
    assert row["evidence_coverage_skipped"] == "no_required_facts"
    assert row.get("evidence_coverage_at_k") != 1
    assert "complete_evidence_at_k" not in row


def test_recall_formula_unchanged_when_coverage_present() -> None:
    labeled = [
        LabeledItem(item_id=10, relevance=3),
        LabeledItem(item_id=20, relevance=1),
        LabeledItem(item_id=30, relevance=2),
    ]
    ranked = [10, 99, 20]
    chunk = retrieval_metrics(ranked, labeled, k=3, granularity="chunk")
    chunk["evidence_coverage_at_k"] = 0.5
    chunk["complete_evidence_at_k"] = False
    aggregated = aggregate_retrieval([chunk], unanswerable_rows=[])
    assert aggregated["metric_version"] == "v4-chunk-ndcg-exp"
    assert aggregated["recall"] == pytest.approx(2 / 3)
    assert aggregated["hit_rate"] == 1.0
    assert aggregated["evidence_coverage"] == pytest.approx(0.5)
    assert aggregated["complete_evidence_rate"] == 0.0
