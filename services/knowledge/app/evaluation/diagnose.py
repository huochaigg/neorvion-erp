"""同题对比、引用存在性检查和无答案结果分类。全部是确定性计算，不调用模型。"""

from __future__ import annotations

import random
import re
from collections import defaultdict

from app.evaluation.context_pack import generation_text
from app.evaluation.judge import looks_like_refusal

_CITATION = re.compile(r"\[(\d{1,3})\]")
_MIN_BOOTSTRAP = 8


def citation_presence(answer: str | None, retrieved_count: int) -> dict:
    """检查回答里的 [n] 是否落在本次召回列表。

    引用序号存在不等于引用内容正确，也不等于 Faithfulness。
    没有 [n] 时记为 no_explicit_citation，不能据此判失败。
    """
    cited = sorted({int(item) for item in _CITATION.findall(answer or "")})
    unknown = [item for item in cited if item < 1 or item > retrieved_count]
    return {
        "cited_ranks": cited,
        "unknown_ranks": unknown,
        "retrieved_count": retrieved_count,
        "status": "no_explicit_citation" if not cited else ("unknown_rank" if unknown else "in_retrieved_context"),
        "note": "只检查引用序号是否属于本次召回，不代表引用能支持事实，也不是 Faithfulness。",
    }


def unanswerable_outcome(*, retrieved_nonempty: bool, answer: str | None) -> dict:
    """区分检索非空、关键词拒答提示和未拒答。关键词命中不是拒答准确率。"""
    hint = looks_like_refusal(answer or "")
    if not answer:
        label = "NO_GENERATION"
    elif retrieved_nonempty and hint:
        label = "NONEMPTY_RETRIEVAL_AND_REFUSAL_HINT"
    elif retrieved_nonempty and not hint:
        label = "NONEMPTY_RETRIEVAL_NO_REFUSAL_HINT"
    elif hint:
        label = "EMPTY_RETRIEVAL_AND_REFUSAL_HINT"
    else:
        label = "EMPTY_RETRIEVAL_NO_REFUSAL_HINT"
    return {
        "retrieved_nonempty": retrieved_nonempty,
        "refusal_keyword_hint": hint,
        "label": label,
        "note": "refusal_keyword_hint 只表示回答含拒答用语，不能当成幻觉率或拒答准确率。",
    }


def _metric(row: dict, key: str) -> float | None:
    metrics = row.get("retrieval_metrics") if isinstance(row.get("retrieval_metrics"), dict) else {}
    value = metrics.get(key)
    if isinstance(value, (int, float)) and key in metrics:
        return float(value)
    return None


def _movement(before: float | None, after: float | None, *, higher_is_better: bool = True) -> str:
    if before is None or after is None:
        return "INCOMPARABLE"
    if after == before:
        return "UNCHANGED"
    improved = after > before if higher_is_better else after < before
    return "IMPROVED" if improved else "REGRESSED"


def align_case_results(baseline: list[dict], candidate: list[dict], *, case_meta: dict[int, dict] | None = None) -> dict:
    """按 case_id 对齐两份结果。召回变化和排序变化分开统计。"""
    meta = case_meta or {}
    left = {int(item["case_id"]): item for item in baseline}
    right = {int(item["case_id"]): item for item in candidate}
    rows = []
    for case_id in sorted(set(left) | set(right)):
        base = left.get(case_id)
        other = right.get(case_id)
        info = meta.get(case_id, {})
        if base is None or other is None:
            rows.append(
                {
                    "case_id": case_id,
                    "question": (base or other or {}).get("question"),
                    "alignment": "MISSING",
                    "recall_movement": "INCOMPARABLE",
                    "rank_movement": "INCOMPARABLE",
                    "question_type": info.get("question_type"),
                    "difficulty": info.get("difficulty"),
                    "tags": info.get("tags") or [],
                }
            )
            continue
        recall_before = _metric(base, "recall")
        recall_after = _metric(other, "recall")
        mrr_before = _metric(base, "mrr")
        mrr_after = _metric(other, "mrr")
        rows.append(
            {
                "case_id": case_id,
                "question": other.get("question") or base.get("question"),
                "alignment": "MATCHED",
                "is_unanswerable": bool(base.get("is_unanswerable") or other.get("is_unanswerable")),
                "question_type": info.get("question_type"),
                "difficulty": info.get("difficulty"),
                "tags": list(info.get("tags") or []),
                "recall_before": recall_before,
                "recall_after": recall_after,
                "recall_delta": None if recall_before is None or recall_after is None else recall_after - recall_before,
                "mrr_before": mrr_before,
                "mrr_after": mrr_after,
                "mrr_delta": None if mrr_before is None or mrr_after is None else mrr_after - mrr_before,
                "recall_movement": _movement(recall_before, recall_after),
                "rank_movement": _movement(mrr_before, mrr_after),
                "baseline_chunk_ids": _chunk_ids(base),
                "candidate_chunk_ids": _chunk_ids(other),
                "baseline_error": base.get("error_message"),
                "candidate_error": other.get("error_message"),
            }
        )
    matched = [item for item in rows if item["alignment"] == "MATCHED"]
    summary = {
        "matched": len(matched),
        "missing": len(rows) - len(matched),
        "recall_improved": sum(1 for item in matched if item["recall_movement"] == "IMPROVED"),
        "recall_regressed": sum(1 for item in matched if item["recall_movement"] == "REGRESSED"),
        "recall_unchanged": sum(1 for item in matched if item["recall_movement"] == "UNCHANGED"),
        "rank_improved": sum(1 for item in matched if item["rank_movement"] == "IMPROVED"),
        "rank_regressed": sum(1 for item in matched if item["rank_movement"] == "REGRESSED"),
        "rank_unchanged": sum(1 for item in matched if item["rank_movement"] == "UNCHANGED"),
    }
    return {
        "cases": rows,
        "summary": summary,
        "groups": _groups(matched),
        "recall_bootstrap": paired_bootstrap_mean(
            [float(item["recall_delta"]) for item in matched if item.get("recall_delta") is not None]
        ),
        "note": "Recall 变化表示命中集合变化；MRR 变化表示排序变化。二者可以不一致。",
    }


def _chunk_ids(row: dict) -> list[int]:
    ids = []
    for item in row.get("retrieved") or []:
        if isinstance(item, dict) and item.get("chunk_id") is not None:
            ids.append(int(item["chunk_id"]))
    return ids


def _groups(rows: list[dict]) -> dict:
    """按题型、难度、标签汇总 Recall 差值。标签题可重复计入多个标签。"""
    return {
        "question_type": _group_by(rows, lambda item: item.get("question_type") or "UNKNOWN"),
        "difficulty": _group_by(rows, lambda item: str(item.get("difficulty") or "UNKNOWN")),
        "tags": _group_tags(rows),
    }


def _group_by(rows: list[dict], key_of) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in rows:
        buckets[str(key_of(item))].append(item)
    return [_bucket(name, items) for name, items in sorted(buckets.items())]


def _group_tags(rows: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in rows:
        tags = item.get("tags") or ["UNTAGGED"]
        for tag in tags:
            buckets[str(tag)].append(item)
    return [_bucket(name, items) for name, items in sorted(buckets.items())]


def _bucket(name: str, items: list[dict]) -> dict:
    deltas = [float(item["recall_delta"]) for item in items if item.get("recall_delta") is not None]
    return {
        "key": name,
        "count": len(items),
        "mean_recall_delta": (sum(deltas) / len(deltas)) if deltas else None,
        "recall_improved": sum(1 for item in items if item.get("recall_movement") == "IMPROVED"),
        "recall_regressed": sum(1 for item in items if item.get("recall_movement") == "REGRESSED"),
    }


def paired_bootstrap_mean(deltas: list[float], *, rounds: int = 1000, seed: int = 8) -> dict:
    """配对差值均值的重抽样区间。样本不足时明确不估计。

    这只描述当前样本的统计波动，不能把微小差值说成检索显著变好。
    """
    if len(deltas) < _MIN_BOOTSTRAP:
        return {
            "available": False,
            "n": len(deltas),
            "reason": f"有效差值不足 {_MIN_BOOTSTRAP} 条，不估计置信区间",
        }
    rng = random.Random(seed)
    means = []
    size = len(deltas)
    for _ in range(rounds):
        sample = [deltas[rng.randrange(size)] for _ in range(size)]
        means.append(sum(sample) / size)
    means.sort()
    low_index = max(0, int(0.025 * (rounds - 1)))
    high_index = min(rounds - 1, int(0.975 * (rounds - 1)))
    return {
        "available": True,
        "n": size,
        "mean": sum(deltas) / size,
        "low": means[low_index],
        "high": means[high_index],
        "rounds": rounds,
        "note": "95% 重抽样区间只表示这批题的统计不确定性，不是业务显著性结论。",
    }


def usage_snapshot(usage: dict | None) -> dict:
    payload = usage if isinstance(usage, dict) else {}
    return {
        "prompt_tokens": payload.get("prompt_tokens"),
        "completion_tokens": payload.get("completion_tokens"),
        "estimated_cost_usd": payload.get("estimated_cost_usd"),
        "token_estimated": bool(payload.get("token_estimated")),
        "latency_p50_ms": payload.get("latency_p50_ms"),
        "latency_p95_ms": payload.get("latency_p95_ms"),
        "failed_count": payload.get("failed_count"),
        "case_count": payload.get("case_count"),
    }


def generation_contexts(retrieved: list[dict]) -> list[str]:
    return [generation_text(item) for item in retrieved if isinstance(item, dict)]
