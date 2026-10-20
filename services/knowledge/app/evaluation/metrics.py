"""检索质量指标。全部按代码定义计算，禁止用 LLM 给这些指标打分。

默认粒度是 Chunk。Document 粒度必须单独调用并在结果中标明 granularity。
相关性：relevance >= 1 视为相关；nDCG 使用 0–3 等级。
无答案题不要调用 retrieval_metrics（相关集合为空时 Recall 分母为零）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

METRIC_VERSION = "v4-chunk-ndcg-exp"


@dataclass(frozen=True)
class LabeledItem:
    item_id: int
    relevance: int


def _relevant_ids(labeled: list[LabeledItem], *, min_relevance: int = 1) -> set[int]:
    return {item.item_id for item in labeled if item.relevance >= min_relevance}


def hit_rate_at_k(ranked_ids: list[int], labeled: list[LabeledItem], k: int) -> float:
    """Hit Rate@K：Top-K 是否至少命中一个相关项。"""
    relevant = _relevant_ids(labeled)
    if k <= 0:
        return 0.0
    return 1.0 if relevant.intersection(ranked_ids[:k]) else 0.0


def recall_at_k(ranked_ids: list[int], labeled: list[LabeledItem], k: int) -> float:
    """Recall@K = |Top-K ∩ 相关| / |全部相关|。相关集合为空时由调用方跳过。"""
    relevant = _relevant_ids(labeled)
    if not relevant:
        raise ValueError("无相关标注，不能计算 Recall")
    if k <= 0:
        return 0.0
    return len(relevant.intersection(ranked_ids[:k])) / len(relevant)


def precision_at_k(ranked_ids: list[int], labeled: list[LabeledItem], k: int) -> float:
    """Precision@K = |Top-K ∩ 相关| / K。K 用配置的截断，不是实际返回条数。"""
    relevant = _relevant_ids(labeled)
    if k <= 0:
        return 0.0
    return len(relevant.intersection(ranked_ids[:k])) / k


def mrr(ranked_ids: list[int], labeled: list[LabeledItem]) -> float:
    """MRR：第一个相关结果排名的倒数；未命中为 0。"""
    relevant = _relevant_ids(labeled)
    for index, item_id in enumerate(ranked_ids, start=1):
        if item_id in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(ranked_ids: list[int], labeled: list[LabeledItem], k: int) -> float:
    """nDCG@K，增益为 2^rel - 1，折损 log2(rank+1)。无正样本时返回 0。"""
    if k <= 0:
        return 0.0
    grades = {item.item_id: max(item.relevance, 0) for item in labeled}
    dcg = 0.0
    for index, item_id in enumerate(ranked_ids[:k], start=1):
        rel = grades.get(item_id, 0)
        dcg += (2**rel - 1) / math.log2(index + 1)
    ideal = sorted((item.relevance for item in labeled if item.relevance > 0), reverse=True)[:k]
    idcg = 0.0
    for index, rel in enumerate(ideal, start=1):
        idcg += (2**rel - 1) / math.log2(index + 1)
    if idcg == 0:
        return 0.0
    return dcg / idcg


def context_precision(ranked_ids: list[int], labeled: list[LabeledItem]) -> float:
    """Context Precision：实际召回列表中相关项占比。空召回为 0。"""
    if not ranked_ids:
        return 0.0
    relevant = _relevant_ids(labeled)
    return len(relevant.intersection(ranked_ids)) / len(ranked_ids)


def context_recall(ranked_ids: list[int], labeled: list[LabeledItem]) -> float:
    """Context Recall：相关项被召回的比例。"""
    return recall_at_k(ranked_ids, labeled, k=max(len(ranked_ids), 1) if ranked_ids else 1)


def retrieval_metrics(
    ranked_ids: list[int],
    labeled: list[LabeledItem],
    *,
    k: int,
    ks: tuple[int, ...] = (1, 3, 5, 10),
    granularity: str = "chunk",
) -> dict:
    """计算一组有监督检索指标。granularity 必须是 chunk 或 document，不得混用。"""
    if granularity not in {"chunk", "document"}:
        raise ValueError("granularity 只能是 chunk 或 document")
    relevant = _relevant_ids(labeled)
    payload: dict = {
        "metric_version": METRIC_VERSION,
        "granularity": granularity,
        "k": k,
        "relevant_count": len(relevant),
        "retrieved_count": len(ranked_ids),
    }
    if not relevant:
        payload["skipped"] = "no_relevant_labels"
        return payload
    payload["hit_rate"] = hit_rate_at_k(ranked_ids, labeled, k)
    payload["recall"] = recall_at_k(ranked_ids, labeled, k)
    payload["precision"] = precision_at_k(ranked_ids, labeled, k)
    payload["mrr"] = mrr(ranked_ids, labeled)
    payload["ndcg"] = ndcg_at_k(ranked_ids, labeled, k)
    payload["context_precision"] = context_precision(ranked_ids[:k], labeled)
    payload["context_recall"] = context_recall(ranked_ids[:k], labeled)
    for cutoff in ks:
        payload[f"hit_rate@{cutoff}"] = hit_rate_at_k(ranked_ids, labeled, cutoff)
        payload[f"recall@{cutoff}"] = recall_at_k(ranked_ids, labeled, cutoff)
        payload[f"precision@{cutoff}"] = precision_at_k(ranked_ids, labeled, cutoff)
        payload[f"ndcg@{cutoff}"] = ndcg_at_k(ranked_ids, labeled, cutoff)
    return payload


def unanswerable_retrieval_stats(ranked_ids: list[int], k: int) -> dict:
    """无答案题不计算 Recall。

    false_recall 只表示 Top-K 非空，不是幻觉率，也不是「召回了错误证据」。
    知识库里本来就可能有无关段落，检索返回它们不等于模型编造了事实。
    """
    top = ranked_ids[:k]
    return {
        "metric_version": METRIC_VERSION,
        "granularity": "chunk",
        "unanswerable": True,
        "false_recall": 1.0 if top else 0.0,
        "false_recall_definition": "top_k_nonempty_not_hallucination_rate",
        "empty_ok": 1.0 if not top else 0.0,
        "retrieved_count": len(top),
    }


def aggregate_retrieval(rows: list[dict], *, unanswerable_rows: list[dict]) -> dict:
    """对可监督题目做宏平均；无答案题单独汇总。"""
    keys = [
        "hit_rate",
        "recall",
        "precision",
        "mrr",
        "ndcg",
        "context_precision",
        "context_recall",
    ]
    result: dict = {
        "metric_version": METRIC_VERSION,
        "granularity": "chunk",
        "supervised_count": len(rows),
        "unanswerable_count": len(unanswerable_rows),
        "comparable": True,
    }
    if rows:
        for key in keys:
            values = [float(row[key]) for row in rows if key in row]
            result[key] = sum(values) / len(values) if values else None
        ks = {int(row["k"]) for row in rows if "k" in row and row["k"] is not None}
        if len(ks) == 1:
            result["k"] = next(iter(ks))
        for cutoff in (1, 3, 5, 10):
            for prefix in ("hit_rate", "recall", "precision", "ndcg"):
                name = f"{prefix}@{cutoff}"
                values = [float(row[name]) for row in rows if name in row]
                if values:
                    result[name] = sum(values) / len(values)
    if unanswerable_rows:
        result["unanswerable_false_recall"] = sum(
            float(row.get("false_recall") or 0) for row in unanswerable_rows
        ) / len(unanswerable_rows)
        result["unanswerable_false_recall_definition"] = "top_k_nonempty_not_hallucination_rate"
        result["unanswerable_empty_ok"] = sum(
            float(row.get("empty_ok") or 0) for row in unanswerable_rows
        ) / len(unanswerable_rows)
    return result
