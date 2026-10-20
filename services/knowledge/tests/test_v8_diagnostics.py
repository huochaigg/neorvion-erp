"""V8 诊断：上下文分离、同题对比、无答案定义、题包校验。不调用外部模型。"""

from __future__ import annotations

from types import SimpleNamespace

from app.evaluation.context_pack import pack_retrieved_hits, retrieval_diagnostics
from app.evaluation.diagnose import (
    align_case_results,
    citation_presence,
    paired_bootstrap_mean,
    unanswerable_outcome,
)
from app.evaluation.metrics import unanswerable_retrieval_stats
from app.evaluation.v8_catalog import experiment_preset_payloads, validate_catalog
from app.processing.extract import pdf_page_warning
from app.services.evaluation_run import _hits_as_objects
from fastapi.testclient import TestClient

from tests.conftest import FakeIdentityClient
from tests.test_evaluation import _create_base, _create_dataset, _grant, _upload


def test_generation_excerpt_is_separate_from_display_snippet() -> None:
    hit = SimpleNamespace(
        chunk_id=1,
        document_id=2,
        filename="a.md",
        content="证据" * 800,
        page_no=1,
        heading="标题",
        version=1,
        final_rank=1,
        vector_score=0.9,
        keyword_score=None,
        rrf_score=None,
        rerank_score=None,
        vector_rank=1,
        keyword_rank=None,
    )
    packed = pack_retrieved_hits([hit], {"judgments": []}, context_budget=1000)
    assert len(packed[0]["content"]) == 500
    assert len(packed[0]["generation_excerpt"]) == 1000
    assert packed[0]["generation_truncated"] is True
    proxy = _hits_as_objects(packed)[0]
    assert proxy.content == packed[0]["generation_excerpt"]
    assert proxy.content != packed[0]["content"]


def test_candidate_diagnostics_keep_ids_not_body() -> None:
    search = SimpleNamespace(
        rerank_applied=True,
        rerank_degraded=False,
        stages={
            "rerank_ms": 12,
            "vector_ranks": [{"chunk_id": 9, "rank": 1, "similarity": 0.8, "content": "不应保存"}],
        },
    )
    packed = [{"chunk_id": 9, "generation_truncated": False}]
    diag = retrieval_diagnostics(search, context_budget=6000, packed=packed)
    assert diag["final_chunk_ids"] == [9]
    assert diag["vector_ranks"][0]["chunk_id"] == 9
    assert "content" not in diag["vector_ranks"][0]


def test_false_recall_is_not_described_as_hallucination() -> None:
    stats = unanswerable_retrieval_stats([1], k=5)
    assert stats["false_recall"] == 1.0
    assert stats["false_recall_definition"] == "top_k_nonempty_not_hallucination_rate"
    outcome = unanswerable_outcome(retrieved_nonempty=True, answer="根据常识，仓库一定支持极速达。")
    assert outcome["label"] == "NONEMPTY_RETRIEVAL_NO_REFUSAL_HINT"
    assert "准确率" in outcome["note"]


def test_citation_presence_does_not_claim_support() -> None:
    found = citation_presence("见 [1] 与 [4]。", 2)
    assert found["status"] == "unknown_rank"
    assert found["unknown_ranks"] == [4]
    assert "Faithfulness" in found["note"]
    assert citation_presence("没有编号", 2)["status"] == "no_explicit_citation"


def test_case_alignment_separates_recall_and_rank() -> None:
    baseline = [
        {"case_id": 1, "question": "甲", "retrieval_metrics": {"recall": 0.5, "mrr": 1.0}, "retrieved": [{"chunk_id": 10}]},
        {"case_id": 2, "question": "乙", "retrieval_metrics": {"recall": 1.0, "mrr": 0.5}, "retrieved": [{"chunk_id": 11}]},
    ]
    candidate = [
        {"case_id": 1, "question": "甲", "retrieval_metrics": {"recall": 1.0, "mrr": 1.0}, "retrieved": [{"chunk_id": 10}, {"chunk_id": 12}]},
        {"case_id": 2, "question": "乙", "retrieval_metrics": {"recall": 1.0, "mrr": 1.0}, "retrieved": [{"chunk_id": 11}]},
    ]
    aligned = align_case_results(
        baseline,
        candidate,
        case_meta={1: {"question_type": "FACTUAL", "difficulty": 2, "tags": ["order"]}, 2: {"question_type": "FACTUAL", "difficulty": 2, "tags": ["order"]}},
    )
    by_id = {item["case_id"]: item for item in aligned["cases"]}
    assert by_id[1]["recall_movement"] == "IMPROVED"
    assert by_id[1]["rank_movement"] == "UNCHANGED"
    assert by_id[2]["recall_movement"] == "UNCHANGED"
    assert by_id[2]["rank_movement"] == "IMPROVED"
    assert aligned["summary"]["recall_improved"] == 1
    assert aligned["summary"]["rank_improved"] == 1


def test_bootstrap_refuses_small_samples() -> None:
    small = paired_bootstrap_mean([0.1, 0.2])
    assert small["available"] is False
    large = paired_bootstrap_mean([0.0, 0.1, 0.0, 0.2, 0.0, 0.0, 0.1, 0.0])
    assert large["available"] is True
    assert large["low"] <= large["mean"] <= large["high"]


def test_v8_catalog_is_traceable_and_not_ready() -> None:
    report = validate_catalog()
    assert report["ok"], report["errors"]
    assert report["ready"] == 0
    assert report["pending_review"] == report["question_count"]
    assert report["missing_chunk_judgments"] == report["question_count"]
    assert report["document_count"] >= 10
    presets = experiment_preset_payloads(5)
    assert [item["config"]["strategy"] for item in presets] == ["VECTOR", "KEYWORD", "HYBRID", "HYBRID"]
    assert presets[-1]["config"]["rerank"] is True
    assert all(item["config"]["evaluate_generation"] is False for item in presets)


def test_pdf_page_warning_does_not_reject() -> None:
    assert pdf_page_warning(10) is None
    assert "没有页数硬限制" in (pdf_page_warning(81) or "")


def test_compare_cases_endpoint_is_tenant_scoped(client: TestClient, identity: FakeIdentityClient) -> None:
    headers = _grant(identity)
    base_id = _create_base(client, headers, "诊断库")
    _doc_id, chunk_id = _upload(client, base_id, headers)
    dataset_id = _create_dataset(client, headers, base_id, "诊断集")
    created = client.post(
        f"/api/v1/evaluation/datasets/{dataset_id}/cases",
        json={"question": "七天无理由怎么退？", "expected_answer": "七日"},
        headers=headers,
    )
    client.put(
        f"/api/v1/evaluation/cases/{created.json()['data']['id']}/judgments",
        json=[{"chunk_id": chunk_id, "relevance": 3}],
        headers=headers,
    )
    runs = []
    for name, strategy in (("诊断A", "KEYWORD"), ("诊断B", "VECTOR")):
        experiment = client.post(
            "/api/v1/evaluation/experiments",
            json={"dataset_id": dataset_id, "name": name, "config": {"strategy": strategy, "top_k": 5, "evaluate_generation": False}},
            headers=headers,
        )
        started = client.post(f"/api/v1/evaluation/experiments/{experiment.json()['data']['id']}/run", headers=headers)
        runs.append(started.json()["data"]["id"])
    compared = client.get(
        "/api/v1/evaluation/compare/cases",
        params={"baseline_id": runs[0], "candidate_id": runs[1]},
        headers=headers,
    )
    assert compared.status_code == 200, compared.text
    body = compared.json()["data"]
    assert body["summary"]["matched"] == 1
    assert body["cases"][0]["baseline_chunk_ids"]
    other = _grant(identity, tenant_id=12, user_id=2)
    hidden = client.get(
        "/api/v1/evaluation/compare/cases",
        params={"baseline_id": runs[0], "candidate_id": runs[1]},
        headers=other,
    )
    assert hidden.status_code == 404
