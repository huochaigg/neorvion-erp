"""V8-R2-120 题包静态校验。不连业务库，不调用模型。"""

from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

from app.models.evaluation import QuestionType
from app.scripts.import_v8_r2_120 import BUCKET_TARGET, DIFF_TARGET, resolve_quote, validate_catalog

CATALOG = Path(__file__).resolve().parents[1] / "eval_fixtures" / "v8-round2" / "r2_120_catalog.py"
DOCS = CATALOG.parent / "docs"
VALID_TYPES = {item.value for item in QuestionType}


def _load():
    spec = importlib.util.spec_from_file_location("r2_120_catalog", CATALOG)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_shape_and_enum_mapping() -> None:
    module = _load()
    validate_catalog(module.QUESTIONS)
    assert module.DATASET_NAME == "V8-R2-120-Comprehensive"
    assert module.KB_NAME == "V8-R2-Multi-Chunk"
    buckets = Counter(item["bucket"] for item in module.QUESTIONS)
    diffs = Counter(item["difficulty_name"] for item in module.QUESTIONS)
    assert buckets == BUCKET_TARGET
    assert diffs == DIFF_TARGET
    assert {item["question_type"] for item in module.QUESTIONS} <= VALID_TYPES
    assert all(item["needs_human_review"] for item in module.QUESTIONS)


def test_gold_quotes_exist_in_source_docs() -> None:
    module = _load()
    files = {path.name: path.read_text(encoding="utf-8") for path in DOCS.glob("*.md")}
    missing = []
    for item in module.QUESTIONS:
        if item["is_unanswerable"]:
            assert item["gold"] == []
            continue
        assert item["gold"], item["external_key"]
        for gold in item["gold"]:
            text = files.get(gold["filename"], "")
            if gold["quote"] not in text:
                missing.append((item["external_key"], gold["filename"], gold["quote"][:80]))
    assert missing == []


def test_unanswerable_and_hallucination_policy() -> None:
    module = _load()
    unanswerable = [item for item in module.QUESTIONS if item["bucket"] == "unanswerable"]
    hall = [item for item in module.QUESTIONS if item["bucket"] == "hallucination"]
    assert len(unanswerable) == 15
    assert all(item["is_unanswerable"] and item["question_type"] == "UNANSWERABLE" for item in unanswerable)
    assert all(not item["gold"] for item in unanswerable)
    assert len(hall) == 15
    assert all(not item["is_unanswerable"] for item in hall)
    assert all(item["gold"] for item in hall)
    assert all(item["question_type"] == "HALLUCINATION" for item in hall)


def test_no_disputed_waiting_return_cancel_item() -> None:
    module = _load()
    disputed = [
        item["external_key"]
        for item in module.QUESTIONS
        if "WAITING_RETURN" in item["question"] and "取消" in item["question"]
    ]
    assert disputed == []


def test_multi_questions_have_multiple_facts() -> None:
    module = _load()
    for item in module.QUESTIONS:
        if item["bucket"] != "multi":
            continue
        assert len(item["required_facts"]) >= 2, item["external_key"]
        assert len(item["gold"]) >= 2, item["external_key"]


def test_overlap_quote_picks_home_chunk() -> None:
    quote = "UNIQUE_RULE_TEXT"
    prefix = "x" * 50
    suffix = "y" * 50
    overlap = quote + "tail"
    chunks = [
        {
            "id": 1,
            "document_id": 10,
            "chunk_index": 0,
            "status": "ACTIVE",
            "enabled": True,
            "filename": "a.md",
            "content": prefix + quote + "body-one" + overlap[-20:],
        },
        {
            "id": 2,
            "document_id": 10,
            "chunk_index": 1,
            "status": "ACTIVE",
            "enabled": True,
            "filename": "a.md",
            "content": overlap + suffix,
        },
    ]
    result = resolve_quote(quote, "a.md", chunks)
    assert result["ok"] is True
    assert result["chunk_id"] == 1
    assert result["reason"] == "overlap-home"


def test_duplicate_expression_keeps_first_chunk_only() -> None:
    quote = "SAME_RULE"
    chunks = [
        {
            "id": 11,
            "document_id": 3,
            "chunk_index": 1,
            "status": "ACTIVE",
            "enabled": True,
            "filename": "b.md",
            "content": "head " + quote + " tail",
        },
        {
            "id": 19,
            "document_id": 3,
            "chunk_index": 8,
            "status": "ACTIVE",
            "enabled": True,
            "filename": "b.md",
            "content": "later " + quote + " again",
        },
    ]
    result = resolve_quote(quote, "b.md", chunks)
    assert result["ok"] is True
    assert result["chunk_id"] == 11
    assert result["reason"] == "duplicate-expression-first"
