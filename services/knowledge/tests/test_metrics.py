"""检索指标必须用确定性样例验证数学定义，禁止用 LLM 打分。"""

from __future__ import annotations

import math

import pytest
from app.evaluation.metrics import (
    LabeledItem,
    aggregate_retrieval,
    hit_rate_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    retrieval_metrics,
    unanswerable_retrieval_stats,
)

LABELED = [
    LabeledItem(item_id=10, relevance=3),
    LabeledItem(item_id=20, relevance=1),
    LabeledItem(item_id=30, relevance=2),
]
# 排名：10 相关，99 无关，20 相关；30 未召回
RANKED = [10, 99, 20]


def test_hit_rate_recall_precision_mrr() -> None:
    assert hit_rate_at_k(RANKED, LABELED, 1) == 1.0
    assert hit_rate_at_k([99, 98], LABELED, 2) == 0.0
    assert recall_at_k(RANKED, LABELED, 3) == pytest.approx(2 / 3)
    assert recall_at_k(RANKED, LABELED, 1) == pytest.approx(1 / 3)
    assert precision_at_k(RANKED, LABELED, 3) == pytest.approx(2 / 3)
    assert precision_at_k([10], LABELED, 3) == pytest.approx(1 / 3)
    assert mrr(RANKED, LABELED) == 1.0
    assert mrr([99, 20], LABELED) == pytest.approx(0.5)
    assert mrr([99, 98], LABELED) == 0.0


def test_ndcg_matches_exponential_gain() -> None:
    dcg = (2**3 - 1) / math.log2(2) + 0.0 / math.log2(3) + (2**1 - 1) / math.log2(4)
    idcg = (2**3 - 1) / math.log2(2) + (2**2 - 1) / math.log2(3) + (2**1 - 1) / math.log2(4)
    assert ndcg_at_k(RANKED, LABELED, 3) == pytest.approx(dcg / idcg)
    assert ndcg_at_k([], LABELED, 3) == 0.0


def test_recall_requires_relevant_labels() -> None:
    with pytest.raises(ValueError, match="无相关标注"):
        recall_at_k([1, 2], [LabeledItem(item_id=1, relevance=0)], 2)


def test_unanswerable_does_not_compute_recall() -> None:
    stats = unanswerable_retrieval_stats([1, 2], k=5)
    assert "recall" not in stats
    assert stats["false_recall"] == 1.0
    empty = unanswerable_retrieval_stats([], k=5)
    assert empty["empty_ok"] == 1.0
    assert empty["false_recall"] == 0.0


def test_retrieval_metrics_keep_granularity() -> None:
    chunk = retrieval_metrics(RANKED, LABELED, k=3, granularity="chunk")
    assert chunk["granularity"] == "chunk"
    assert chunk["hit_rate"] == 1.0
    assert chunk["recall"] == pytest.approx(2 / 3)
    document = retrieval_metrics([1, 2], [LabeledItem(item_id=1, relevance=2)], k=2, granularity="document")
    assert document["granularity"] == "document"
    skipped = retrieval_metrics([1], [], k=3)
    assert skipped["skipped"] == "no_relevant_labels"


def test_aggregate_separates_unanswerable() -> None:
    supervised = [retrieval_metrics(RANKED, LABELED, k=3)]
    unanswerable = [unanswerable_retrieval_stats([1], 3)]
    aggregated = aggregate_retrieval(supervised, unanswerable_rows=unanswerable)
    assert aggregated["supervised_count"] == 1
    assert aggregated["unanswerable_count"] == 1
    assert aggregated["k"] == 3
    assert aggregated["recall"] == pytest.approx(2 / 3)
    assert aggregated["unanswerable_false_recall"] == 1.0
    assert aggregated["granularity"] == "chunk"
