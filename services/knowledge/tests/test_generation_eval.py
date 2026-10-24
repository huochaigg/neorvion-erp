"""R2-06 生成评测：Prompt 不泄漏标准答案、引用可追溯、Context 与 Chat 一致。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.evaluation import ExperimentConfigIn, POSTGRES_INT32_MAX
from app.evaluation.citation import citation_metrics
from app.evaluation.generation import (
    absent_terms_from_case,
    aggregate_generation,
    fabricated_terms,
    is_false_premise_case,
)
from app.evaluation.judge import JUDGE_PROMPT_VERSION, build_judge_messages
from app.evaluation.context_pack import pack_retrieved_hits, prompt_observability
from app.evaluation.prompt import (
    SYSTEM_PROMPT,
    assert_no_answer_leak,
    build_rag_messages,
    format_evidence_block,
    pack_prompt_hits,
    select_prompt_hits,
)
from app.services.evaluation_run import _filter_eval_cases
from app.services.retrieval import RetrievedHit


def _hit(
    chunk_id: int,
    content: str,
    filename: str = "a.md",
    *,
    document_id: int = 1,
    heading: str = "规则",
) -> RetrievedHit:
    return RetrievedHit(
        chunk_id=chunk_id,
        document_id=document_id,
        knowledge_base_id=8,
        filename=filename,
        content=content,
        page_no=1,
        heading=heading,
        chunk_index=0,
        version=1,
        final_rank=chunk_id,
    )


def test_generate_prompt_excludes_expected_answer() -> None:
    gold = "标准答案：确认发货不会再扣库存。"
    trace = build_rag_messages("确认发货会再扣库存吗？", [_hit(64, "出库已经扣过账面库存。")])
    blob = "\n".join(item["content"] for item in trace.messages)
    assert gold not in blob
    assert "<gold>" not in blob
    assert "标准答案：" not in blob
    assert trace.messages[-1]["content"] == "确认发货会再扣库存吗？"
    assert SYSTEM_PROMPT in trace.messages[0]["content"]
    assert_no_answer_leak(trace.messages, gold)


def test_assert_no_answer_leak_raises() -> None:
    with pytest.raises(ValueError, match="泄漏"):
        assert_no_answer_leak([{"role": "user", "content": "七日可退"}], "七日可退")


def test_judge_prompt_keeps_gold_and_false_premise_branch() -> None:
    messages = build_judge_messages(
        question="确认发货会再扣库存吗？",
        answer="会再扣一次。",
        contexts=["出库已经扣过账面库存。"],
        expected_answer="前提错误。确认发货不再改 Inventory。",
        is_unanswerable=False,
        is_false_premise=True,
    )
    blob = "\n".join(item["content"] for item in messages)
    assert "<gold>" in blob
    assert "错误前提" in blob
    assert "不应只拒答" in blob
    assert JUDGE_PROMPT_VERSION in messages[0]["content"]
    unanswerable = build_judge_messages(
        question="仓库面积多少？",
        answer="大概 2000 平方米。",
        contexts=["出库规则"],
        expected_answer="知识库未记载面积。",
        is_unanswerable=True,
        is_false_premise=False,
    )
    note = "\n".join(item["content"] for item in unanswerable)
    assert "无答案题" in note
    assert "不能因此判幻觉" in note


def test_context_builder_is_all_or_nothing() -> None:
    first = _hit(1, "A" * 200)
    second = _hit(2, "B" * 200)
    selected, used = select_prompt_hits([first, second], budget=80)
    assert selected == []
    assert used == 0
    packed = pack_prompt_hits([first, second], budget=80)
    assert packed.context_budget_limited is True
    assert packed.truncation_reason == "budget"
    assert packed.omitted_chunk_count == 2
    assert packed.partially_truncated_chunk_count == 0
    included, _ = select_prompt_hits([first, second], budget=2000)
    assert [item.chunk_id for item in included] == [1, 2]
    tight, _ = select_prompt_hits([first, second], budget=len(format_evidence_block(1, first)) + 10)
    assert [item.chunk_id for item in tight] == [1]


def test_context_builder_skips_over_oversized_chunk() -> None:
    huge = _hit(1, "H" * 400, document_id=11)
    small = _hit(2, "短证据", document_id=12)
    packed = pack_prompt_hits([huge, small], budget=len(format_evidence_block(1, small)) + 20)
    assert [item.chunk_id for item in packed.selected] == [2]
    assert packed.omitted_reasons[1] == "budget"
    assert packed.context_budget_limited is True
    assert packed.partially_truncated_chunk_count == 0


def test_context_builder_skips_duplicate_and_empty() -> None:
    first = _hit(1, "同一段证据" * 8, document_id=3)
    duplicate = _hit(2, "同一段证据" * 8, document_id=3)
    empty = _hit(3, "   ", document_id=4)
    packed = pack_prompt_hits([first, duplicate, empty], budget=4000)
    assert [item.chunk_id for item in packed.selected] == [1]
    assert packed.omitted_reasons[2] == "duplicate"
    assert packed.omitted_reasons[3] == "empty"
    assert packed.context_budget_limited is False
    assert packed.truncation_reason == "other"


def test_context_builder_does_not_swap_higher_ranked_chunks_for_tail() -> None:
    hits = [
        _hit(10, "A" * 220, filename="one.md", document_id=1),
        _hit(11, "B" * 220, filename="one.md", document_id=1),
        _hit(12, "C" * 220, filename="one.md", document_id=1),
        _hit(20, "D" * 80, filename="two.md", document_id=2),
    ]
    block = format_evidence_block(1, hits[0])
    budget = len(block) * 3 + 40
    packed = pack_prompt_hits(hits, budget=budget)
    assert packed.prompt_ids == [10, 11, 12]
    assert packed.omitted_reasons[20] == "budget"


def test_prompt_observability_uses_packed_flags_not_filtered_trace() -> None:
    hits = [_hit(1, "证据" * 80, document_id=1), _hit(2, "尾巴" * 80, document_id=2)]
    packed_rows = pack_retrieved_hits(hits, {"judgments": []}, context_budget=len(format_evidence_block(1, hits[0])) + 10)
    assert packed_rows[0]["in_prompt"] is True
    assert packed_rows[1]["in_prompt"] is False
    filtered_trace = build_rag_messages("问？", [hits[0]], budget=6000)
    assert filtered_trace.truncated is False
    stats = prompt_observability(packed_rows, filtered_trace)
    assert stats["prompt_truncated"] is True
    assert stats["context_budget_limited"] is True
    assert stats["omitted_chunk_ids"] == [2]
    assert stats["retrieved_chunk_ids"] == [1, 2]
    assert stats["truncation_reason"] == "budget"
    assert stats["partially_truncated_chunk_count"] == 0


def test_chat_and_eval_share_packing() -> None:
    hits = [_hit(8, "完整切片正文", document_id=8), _hit(9, "另一文档", document_id=9)]
    eval_ids = pack_prompt_hits(hits, budget=6000).prompt_ids
    from app.services.chat import ChatService

    dummy = ChatService.__new__(ChatService)
    trace = ChatService._build_messages(dummy, "问题", hits, [])
    assert trace.prompt_chunk_ids == eval_ids
    assert "完整切片正文" in trace.messages[1]["content"]


def test_citation_correctness_is_not_a_count() -> None:
    none = citation_metrics("没有编号。", [10, 11], gold_chunk_ids=[10])
    assert none["citation_correctness"] is None
    assert none["citation_correctness_skipped"] == "no_explicit_citation"
    assert none["citation_validity"] is None
    assert none["gold_citation_match"] is None
    assert none["claim_support"] is None
    assert none["claim_support_skipped"] == "not_evaluated"
    valid = citation_metrics("见 [1]。", [10, 11], gold_chunk_ids=[10], support_chunk_ids=[10])
    assert valid["cited_chunk_ids"] == [10]
    assert valid["citation_correctness"] == 1.0
    assert valid["citation_validity"] == 1.0
    assert valid["gold_citation_match"] == 1.0
    assert valid["claim_support"] is None
    wrong = citation_metrics("见 [2]。", [10, 11], gold_chunk_ids=[10], support_chunk_ids=[10])
    assert wrong["cited_chunk_ids"] == [11]
    assert wrong["citation_correctness"] == 0.0
    assert wrong["citation_validity"] == 1.0
    assert wrong["gold_citation_match"] == 0.0
    invalid = citation_metrics("见 [9]。", [10], gold_chunk_ids=[10])
    assert invalid["invalid_ranks"] == [9]
    assert invalid["citation_correctness"] == 0.0
    assert invalid["citation_validity"] == 0.0
    unanswerable = citation_metrics("见 [1]。", [10], gold_chunk_ids=[], is_unanswerable=True)
    assert unanswerable["citation_correctness"] is None
    assert unanswerable["gold_citation_match"] is None
    assert unanswerable["citation_validity"] == 1.0
    assert unanswerable["status"] == "unanswerable_with_citation"
    assert unanswerable["claim_support_skipped"] == "not_evaluated"


def test_fabricated_terms_and_false_premise_detection() -> None:
    found = fabricated_terms(
        "深圳仓有 3000 平方米。",
        ["平方米", "面积"],
        question="深圳仓的仓储建筑面积是多少平方米？",
    )
    assert found["fabricated"] is True
    assert found["fabricated_status"] == "likely_fabricated"
    assert any("3000" in item for item in found["fabricated_terms"])
    assert "面积" not in found["fabricated_terms"]
    clean = fabricated_terms("知识库没有该项数字记载。", ["平方米", "面积"])
    assert clean["fabricated"] is False
    assert clean["fabricated_status"] == "not_fabricated"
    refuse_area = fabricated_terms(
        "知识库证据不足，无法回答深圳仓的仓储建筑面积。现有摘录未提供任何仓库建筑面积数据。[1][4][6]",
        ["平方米", "面积", "库容"],
        question="深圳仓的仓储建筑面积是多少平方米？",
    )
    assert refuse_area["fabricated"] is False
    assert refuse_area["fabricated_status"] == "not_fabricated"
    assert refuse_area["fabricated_terms"] == []
    refuse_hotline = fabricated_terms(
        "知识库证据不足，无法回答客服热线工作时间的问题。现有摘录没有包含客服热线或其工作时间的信息。",
        ["热线", "工作时间"],
        question="客服热线的工作时间是几点到几点？",
    )
    assert refuse_hotline["fabricated"] is False
    assert refuse_hotline["fabricated_status"] == "not_fabricated"
    promo = fabricated_terms(
        "知识库证据不足：现有摘录没有提到“促销满 300 减 50”这类促销规则的配置表，无法据此回答维护位置。",
        ["促销", "满减"],
        question="促销满 300 减 50 要在哪个配置表里维护？",
    )
    assert promo["fabricated"] is False
    assert promo["fabricated_status"] == "not_fabricated"
    assert promo["fabricated_terms"] == []
    chinese_restated = fabricated_terms(
        "知识库没有记载满三百减五十的配置。",
        ["促销"],
        question="促销满 300 减 50 要在哪个配置表里维护？",
    )
    assert chinese_restated["fabricated"] is False
    price = fabricated_terms(
        "知识库证据不足，没有 99 元包邮的运费规则。",
        ["运费"],
        question="99元包邮在哪个表配置？",
    )
    assert price["fabricated"] is False
    phone_ok = fabricated_terms(
        "知识库未记载客服热线 400-800-1234。",
        ["热线"],
        question="客服热线 400-800-1234 的工作时间是几点？",
    )
    assert phone_ok["fabricated"] is False
    negation = fabricated_terms(
        "不能把满300减50当成知识库已有规则，证据不足无法回答。",
        ["促销"],
        question="促销满300减50要在哪个配置表里维护？",
    )
    assert negation["fabricated"] is False
    invented_time = fabricated_terms(
        "客服热线工作时间是 9:00 到 18:00。",
        ["热线"],
        question="客服热线的工作时间是几点到几点？",
    )
    assert invented_time["fabricated"] is True
    review_claim = fabricated_terms(
        "满 300 减 50 应该写在促销配置表。",
        ["促销"],
        question="促销满 300 减 50 要在哪个配置表里维护？",
    )
    assert review_claim["fabricated"] is None
    assert review_claim["fabricated_status"] == "needs_review"
    invented_hours = fabricated_terms(
        "客服热线工作时间是 9:00 到 18:00。",
        ["热线", "工作时间"],
        question="客服热线的工作时间是几点到几点？",
    )
    assert invented_hours["fabricated"] is True
    assert invented_hours["fabricated_status"] == "likely_fabricated"
    invented_phone = fabricated_terms(
        "请拨打客服热线 400-800-1234。",
        ["热线"],
        question="客服热线的工作时间是几点到几点？",
    )
    assert invented_phone["fabricated"] is True
    review = fabricated_terms(
        "客服热线由总部统一安排。",
        ["热线", "工作时间"],
        question="客服热线的工作时间是几点到几点？",
    )
    assert review["fabricated"] is None
    assert review["fabricated_status"] == "needs_review"
    empty = fabricated_terms("", ["面积"])
    assert empty["fabricated"] is None
    assert empty["fabricated_status"] == "unknown"
    assert is_false_premise_case({"question_type": "HALLUCINATION"}) is True
    assert is_false_premise_case({"question_type": "FACTUAL", "tags": ["bucket:hallucination"]}) is True
    assert is_false_premise_case({"question_type": "UNANSWERABLE"}) is False
    catalog_terms = absent_terms_from_case({"question": "深圳仓的仓储建筑面积是多少平方米？", "tags": []})
    assert "平方米" in catalog_terms
    assert "面积" in catalog_terms


def test_aggregate_generation_skips_null_and_keyword_refusal() -> None:
    rows = [
        {
            "faithfulness": 0.9,
            "answer_relevancy": 0.8,
            "answer_correctness": 0.7,
            "citation_correctness": None,
            "is_unanswerable": True,
            "refused": True,
        },
        {
            "faithfulness": 0.5,
            "answer_relevancy": 0.4,
            "answer_correctness": None,
            "citation_correctness": 0.0,
            "is_unanswerable": True,
            "refused": False,
            "refusal_keyword_hint": True,
        },
        {
            "faithfulness": 1.0,
            "is_false_premise": True,
            "false_premise_identified": True,
            "correction_correctness": 0.8,
        },
    ]
    agg = aggregate_generation(rows)
    assert agg["faithfulness"] == pytest.approx(0.8)
    assert agg["citation_correctness"] == 0.0
    assert agg["citation_correctness_count"] == 1
    assert agg["claim_support"] is None
    assert agg["claim_support_skipped"] == "not_evaluated"
    assert agg["gold_citation_match_note"].startswith("gold_citation_match")
    assert agg["refusal_accuracy"] == pytest.approx(0.5)
    assert agg["refusal_accuracy_definition"].startswith("judge_refused")
    assert agg["false_premise_correction_rate"] == pytest.approx(0.8)


def test_case_ids_filter_keeps_ready_subset() -> None:
    cases = [
        {"id": 1, "annotation_status": "READY"},
        {"id": 2, "annotation_status": "READY"},
        {"id": 3, "annotation_status": "LABELED"},
    ]
    assert [item["id"] for item in _filter_eval_cases(cases, {})] == [1, 2]
    assert [item["id"] for item in _filter_eval_cases(cases, {"case_ids": [2, 1]})] == [2, 1]
    with pytest.raises(AppError) as exc:
        _filter_eval_cases(cases, {"case_ids": [3]})
    assert exc.value.code == 40086


def test_chat_and_eval_share_system_prompt() -> None:
    from app.services.chat import _SYSTEM

    assert _SYSTEM == SYSTEM_PROMPT
    hit = SimpleNamespace(
        chunk_id=8,
        filename="doc.md",
        page_no=1,
        heading="h",
        version=1,
        content="完整切片正文",
    )
    from app.services.chat import ChatService

    class _Dummy:
        pass

    dummy = ChatService.__new__(ChatService)
    trace = ChatService._build_messages(dummy, "问题", [hit], [])
    assert trace.prompt_chunk_ids == [8]
    assert "完整切片正文" in trace.messages[1]["content"]
    assert trace.messages[-1]["content"] == "问题"


def test_token_budget_one_million_fits_postgres_integer() -> None:
    cfg = ExperimentConfigIn(token_budget=1_000_000)
    assert cfg.token_budget == 1_000_000
    assert 1_000_000 <= POSTGRES_INT32_MAX
    with pytest.raises(ValidationError):
        ExperimentConfigIn(token_budget=POSTGRES_INT32_MAX + 1)
