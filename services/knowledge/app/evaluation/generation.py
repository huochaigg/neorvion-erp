"""生成质量的确定性部分与宏平均。Judge 分数另行合并，失败不得伪造。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app.evaluation.evidence import evidence_coverage_metrics
from app.models.evaluation import QuestionType

GENERATION_METRIC_VERSION = "v3-gen-r2-08"

_CITATION_MARK = re.compile(r"\[\d{1,3}\]")
_PHONE = re.compile(
    r"(?:\+?86[-\s]?)?(?:1[3-9]\d{9}|400[-\s]?\d{3,4}[-\s]?\d{3,4}|0\d{2,3}[-\s]?\d{7,8})"
)
_CLOCK_TIME = re.compile(
    r"(?:[01]?\d|2[0-3])[:：时点][0-5]?\d"
    r"(?:\s*[-~～至到]\s*(?:[01]?\d|2[0-3])[:：时点][0-5]?\d)?"
)
_CHINESE_CLOCK = re.compile(
    r"[零一二三四五六七八九十两]{1,3}\s*点(?:整|[零一二三四五六七八九十]+分)?"
    r"(?:\s*[至到]\s*[零一二三四五六七八九十两]{1,3}\s*点(?:整|[零一二三四五六七八九十]+分)?)?"
)
_QUANTITY = re.compile(
    r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百千万两零]+(?:点[一二三四五六七八九十]+)?)"
    r"\s*(?:平方米|平米|m²|㎡|小时|分钟|天|元|万元|公斤|吨|%|％)"
)
_BARE_NUMBER = re.compile(r"\d{2,}(?:\.\d+)?")
_REFUSAL_HINTS = (
    "无法回答",
    "证据不足",
    "未记载",
    "没有记载",
    "不包含",
    "未提供",
    "没有包含",
    "知识库没有",
    "现有摘录没有",
    "不能回答",
    "无法给出",
    "没有该项",
    "未给出",
    "没有相关",
    "知识库不包含",
    "没有该项数字",
)


@lru_cache(maxsize=1)
def _catalog_absent_terms() -> dict[str, tuple[str, ...]]:
    """用题面匹配工作稿中的缺失专名。不改冻结快照。"""
    path = Path(__file__).resolve().parents[2] / "eval_fixtures" / "v8-round2" / "r2_120_catalog.py"
    if not path.exists():
        return {}
    import importlib.util

    spec = importlib.util.spec_from_file_location("r2_120_catalog_absent", path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    mapping: dict[str, tuple[str, ...]] = {}
    for item in getattr(module, "QUESTIONS", []):
        question = str(item.get("question") or "").strip()
        terms = tuple(str(term) for term in (item.get("absent_terms") or []) if term)
        if question and terms:
            mapping[question] = terms
    return mapping


def absent_terms_from_case(case: dict) -> list[str]:
    terms: list[str] = []
    for tag in case.get("tags") or []:
        text = str(tag)
        if text.startswith("absent:"):
            value = text.split(":", 1)[1].strip()
            if value and value not in terms:
                terms.append(value)
    for item in case.get("absent_terms") or []:
        value = str(item).strip()
        if value and value not in terms:
            terms.append(value)
    if not terms:
        catalog = _catalog_absent_terms().get(str(case.get("question") or "").strip())
        if catalog:
            terms.extend(catalog)
    return terms


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        value = item.strip()
        if value and value not in seen:
            seen.append(value)
    return seen


def _looks_like_refusal(text: str) -> bool:
    return any(hint in text for hint in _REFUSAL_HINTS)


_CN_DIGIT = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CN_NUMBER = re.compile(r"[零〇一二三四五六七八九十百千万两]+")


def _chinese_number_to_int(token: str) -> int | None:
    text = token.strip()
    if not text or any(char not in _CN_DIGIT and char not in {"十", "百", "千", "万"} for char in text):
        return None
    if text in _CN_DIGIT:
        return _CN_DIGIT[text]
    total = 0
    current = 0
    for char in text:
        if char in _CN_DIGIT:
            current = _CN_DIGIT[char]
            continue
        if char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
        elif char == "千":
            total += (current or 1) * 1000
            current = 0
        elif char == "万":
            total = (total + current) * 10000
            current = 0
        else:
            return None
    return total + current


def _specific_assertions(text: str) -> list[str]:
    """只收集具体数值、时刻、电话等断言，忽略 [n] 引用序号。"""
    body = _CITATION_MARK.sub(" ", text)
    found: list[str] = []
    for pattern in (_PHONE, _CLOCK_TIME, _CHINESE_CLOCK, _QUANTITY):
        found.extend(match.group(0) for match in pattern.finditer(body))
    covered = " ".join(found)
    for match in _BARE_NUMBER.finditer(body):
        token = match.group(0)
        if token in covered:
            continue
        found.append(token)
    for match in _CN_NUMBER.finditer(body):
        token = match.group(0)
        if len(token) < 2 or token in covered or _chinese_number_to_int(token) is None:
            continue
        found.append(token)
    return _unique(found)


def _digits_only(text: str) -> str:
    return re.sub(r"\D+", "", text)


def _assertion_keys(token: str) -> set[str]:
    keys = {token, token.replace(" ", ""), _digits_only(token)}
    parsed = _chinese_number_to_int(token)
    if parsed is not None:
        keys.add(str(parsed))
    digits = _digits_only(token)
    if digits.isdigit():
        keys.add(digits.lstrip("0") or "0")
    return {item for item in keys if item}


def _is_restated_assertion(token: str, question: str, question_keys: set[str]) -> bool:
    if not token:
        return False
    compact_question = question.replace(" ", "")
    if token in question or token.replace(" ", "") in compact_question:
        return True
    return bool(_assertion_keys(token) & question_keys)


def fabricated_terms(answer: str | None, terms: list[str], *, question: str | None = None) -> dict:
    """无答案题的确定性编造检查。拒答里复述题面数字/主题词不算编造。"""
    text = answer or ""
    question_text = question or ""
    checked = list(terms)
    topic_hits = [term for term in checked if term and term in text]
    restated = [term for term in topic_hits if term in question_text]
    question_assertions = _specific_assertions(question_text)
    question_keys: set[str] = set()
    for item in [question_text, *question_assertions]:
        question_keys.update(_assertion_keys(item))
    question_keys.update({part for part in _digits_only(question_text).split() if part})
    if _digits_only(question_text):
        question_keys.add(_digits_only(question_text))
    note = (
        "只把缺乏证据的具体数值、时刻、电话或同类断言记为可能编造；"
        "拒答中重复题面已出现的数字、价格、时间或「面积」「热线」等主题词不算编造。"
        "引用编号已忽略。不能可靠判断时为 needs_review，不强行 fabricated=true。"
    )
    if not text.strip():
        return {
            "checked_terms": checked,
            "fabricated_terms": [],
            "fabricated_assertions": [],
            "restated_topic_terms": restated,
            "restated_assertions": [],
            "fabricated": None,
            "fabricated_status": "unknown",
            "note": note,
        }
    assertions = _specific_assertions(text)
    restated_assertions = [item for item in assertions if _is_restated_assertion(item, question_text, question_keys)]
    novel_assertions = [item for item in assertions if item not in restated_assertions]
    if novel_assertions:
        return {
            "checked_terms": checked,
            "fabricated_terms": novel_assertions,
            "fabricated_assertions": novel_assertions,
            "restated_topic_terms": restated,
            "restated_assertions": restated_assertions,
            "fabricated": True,
            "fabricated_status": "likely_fabricated",
            "note": note,
        }
    if _looks_like_refusal(text):
        return {
            "checked_terms": checked,
            "fabricated_terms": [],
            "fabricated_assertions": [],
            "restated_topic_terms": restated or topic_hits,
            "restated_assertions": restated_assertions,
            "fabricated": False,
            "fabricated_status": "not_fabricated",
            "note": note,
        }
    if restated_assertions or topic_hits:
        return {
            "checked_terms": checked,
            "fabricated_terms": [],
            "fabricated_assertions": [],
            "restated_topic_terms": restated or topic_hits,
            "restated_assertions": restated_assertions,
            "fabricated": None,
            "fabricated_status": "needs_review",
            "note": note,
        }
    return {
        "checked_terms": checked,
        "fabricated_terms": [],
        "fabricated_assertions": [],
        "restated_topic_terms": restated,
        "restated_assertions": [],
        "fabricated": False,
        "fabricated_status": "not_fabricated",
        "note": note,
    }


def is_false_premise_case(case: dict) -> bool:
    if str(case.get("question_type") or "") == QuestionType.HALLUCINATION.value:
        return True
    tags = [str(item) for item in case.get("tags") or []]
    return any(tag == "bucket:hallucination" or tag.startswith("bucket:hallucination") for tag in tags)


def gold_chunk_ids(case: dict) -> list[int]:
    ids: list[int] = []
    for item in case.get("judgments") or []:
        if item.get("stale"):
            continue
        if int(item.get("relevance") or 0) < 1:
            continue
        chunk_id = item.get("chunk_id")
        if chunk_id is None:
            continue
        ids.append(int(chunk_id))
    return ids


def support_chunk_ids(case: dict, *, valid_chunk_ids: set[int] | None = None) -> list[int]:
    """primary + alternative；partial 不计入可支持引用。"""
    from app.evaluation.evidence import parse_case_evidence

    spec = parse_case_evidence(case)
    allowed = valid_chunk_ids
    ids: list[int] = []
    if spec is None:
        return gold_chunk_ids(case)
    for fact in spec.facts:
        for chunk_id in (*fact.primary_chunk_ids, *fact.alternative_chunk_ids):
            if allowed is not None and chunk_id not in allowed:
                continue
            if chunk_id not in ids:
                ids.append(chunk_id)
    return ids or gold_chunk_ids(case)


def prompt_evidence_coverage(
    prompt_chunk_ids: list[int],
    case: dict,
    *,
    valid_chunk_ids: set[int],
    rejected: dict | None = None,
) -> dict:
    """对实际进入 Prompt 的 Chunk 再算一遍 Coverage，与检索 Top-K Coverage 分开。"""
    if case.get("is_unanswerable"):
        return evidence_coverage_metrics([], None, k=0, valid_chunk_ids=set(), is_unanswerable=True)
    spec = None
    from app.evaluation.evidence import parse_case_evidence

    spec = parse_case_evidence(case)
    k = max(len(prompt_chunk_ids), 1)
    coverage = evidence_coverage_metrics(
        prompt_chunk_ids,
        spec,
        k=k,
        valid_chunk_ids=valid_chunk_ids,
        rejected=rejected,
        is_unanswerable=False,
    )
    renamed = dict(coverage)
    if "evidence_coverage_at_k" in renamed:
        renamed["prompt_evidence_coverage_at_k"] = renamed.pop("evidence_coverage_at_k")
    if "complete_evidence_at_k" in renamed:
        renamed["prompt_complete_evidence_at_k"] = renamed.pop("complete_evidence_at_k")
    if renamed.get("evidence_coverage_skipped"):
        renamed["prompt_evidence_coverage_skipped"] = renamed.get("evidence_coverage_skipped")
    renamed["prompt_chunk_ids"] = list(prompt_chunk_ids)
    renamed["prompt_k"] = len(prompt_chunk_ids)
    return renamed


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate_generation(rows: list[dict]) -> dict:
    """宏平均生成指标。None 不按 0 计入。keyword 拒答提示不是 Refusal Accuracy。"""
    payload: dict = {
        "generation_metric_version": GENERATION_METRIC_VERSION,
        "subjective": True,
        "scored_count": 0,
        "judge_failed_count": 0,
        "judge_skipped_count": 0,
    }
    for key in (
        "faithfulness",
        "answer_relevancy",
        "answer_correctness",
        "citation_correctness",
        "citation_validity",
        "gold_citation_match",
        "correction_correctness",
    ):
        values = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float))]
        payload[key] = _mean(values)
        payload[f"{key}_count"] = len(values)
    payload["claim_support"] = None
    payload["claim_support_skipped"] = "not_evaluated"
    payload["gold_citation_match_note"] = (
        "gold_citation_match 是引用是否命中 primary/alternative，不能当作真实引用正确率。"
    )
    judged = [row for row in rows if row.get("judge_skipped") is not True and row.get("faithfulness") is not None]
    payload["scored_count"] = len(judged)
    payload["judge_failed_count"] = sum(1 for row in rows if row.get("judge_error"))
    payload["judge_skipped_count"] = sum(1 for row in rows if row.get("judge_skipped"))

    unanswerable = [row for row in rows if row.get("is_unanswerable")]
    scored_unanswerable = [
        row
        for row in unanswerable
        if row.get("refused") is not None and not row.get("judge_error")
    ]
    if scored_unanswerable:
        payload["refusal_accuracy"] = sum(1.0 if row.get("refused") else 0.0 for row in scored_unanswerable) / len(
            scored_unanswerable
        )
        payload["refusal_accuracy_count"] = len(scored_unanswerable)
        payload["refusal_accuracy_definition"] = "judge_refused_on_unanswerable_not_keyword_hint"
    else:
        payload["refusal_accuracy"] = None

    false_premise = [row for row in rows if row.get("is_false_premise")]
    identified = [row for row in false_premise if row.get("false_premise_identified") is not None and not row.get("judge_error")]
    if identified:
        payload["false_premise_identified_rate"] = sum(
            1.0 if row.get("false_premise_identified") else 0.0 for row in identified
        ) / len(identified)
        payload["false_premise_identified_count"] = len(identified)
    corrections = [
        float(row["correction_correctness"])
        for row in false_premise
        if isinstance(row.get("correction_correctness"), (int, float))
    ]
    payload["false_premise_correction_rate"] = _mean(corrections)
    payload["false_premise_count"] = len(false_premise)

    prompt_cov = [
        float(row["prompt_evidence_coverage_at_k"])
        for row in rows
        if isinstance(row.get("prompt_evidence_coverage_at_k"), (int, float))
    ]
    payload["prompt_evidence_coverage"] = _mean(prompt_cov)
    complete_prompt = [
        1.0 if row.get("prompt_complete_evidence_at_k") else 0.0
        for row in rows
        if row.get("prompt_complete_evidence_at_k") is not None
        and row.get("prompt_evidence_coverage_skipped") in {None, False}
        and isinstance(row.get("prompt_evidence_coverage_at_k"), (int, float))
    ]
    payload["prompt_complete_evidence_rate"] = _mean(complete_prompt)
    payload["prompt_truncated_rate"] = (
        sum(1.0 if row.get("prompt_truncated") or row.get("context_budget_limited") else 0.0 for row in rows) / len(rows)
        if rows
        else None
    )
    omitted_counts = [
        int(row["omitted_chunk_count"])
        for row in rows
        if isinstance(row.get("omitted_chunk_count"), (int, float))
    ]
    payload["mean_omitted_chunk_count"] = _mean([float(item) for item in omitted_counts])
    payload["context_budget_limited_rate"] = payload["prompt_truncated_rate"]
    payload["fabricated_unanswerable_count"] = sum(1 for row in unanswerable if row.get("fabricated") is True)
    payload["fabricated_review_count"] = sum(
        1 for row in unanswerable if row.get("fabricated_status") in {"needs_review", "unknown"}
    )
    payload["note"] = (
        "Faithfulness / Correctness / Relevancy 来自 LLM Judge，具有主观性。"
        "citation_correctness 是历史兼容字段，等于 gold 命中率，不是真实引用正确率。"
        "citation_validity 只检查编号是否落在本次 Prompt；claim_support 当前未评测。"
        "Refusal Accuracy 只用 Judge 的 refused，不用关键词拒答提示。"
    )
    return payload
