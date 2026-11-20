from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
from app.ai.types import ChatDelta, ModelMessage, ModelToolDefinition
from app.core.config import settings
from app.core.exceptions import AppError
from app.evaluation.metrics import aggregate_metrics, evaluate_case
from app.schemas.evaluation import EvaluationRunCreate
from app.services.evaluations import AgentEvaluationService
from app.skills.catalog import SkillCatalogEntry
from app.skills.classification import TaskClassifier
from app.skills.inputs import SkillInputCollector
from app.skills.orchestration import _topological_levels
from app.skills.selector import SkillSelector


def _catalog() -> list[SkillCatalogEntry]:
    return [
        SkillCatalogEntry(1, 11, "inventory-analysis", "库存风险分析", "分析 SKU 库存覆盖天数、缺货和库存风险", 1),
        SkillCatalogEntry(2, 22, "sales-order-review", "销售订单审查", "读取销售订单并审查异常和履约风险", 1),
        SkillCatalogEntry(3, 33, "knowledge-research", "授权知识研究", "查询知识库制度、政策、流程并返回引用", 1),
        SkillCatalogEntry(4, 44, "supplier-risk", "供应商风险研究", "研究供应商交期、质量和采购风险", 1),
    ]


def test_intent_complexity_risk_is_routing_signal_not_authorization() -> None:
    classifier = TaskClassifier()
    read = classifier.classify("查看订单 SO-001 是否异常")
    assert read.intent == "ORDER_REVIEW"
    assert read.risk == "READ_ONLY"
    write = classifier.classify("把订单 SO-001 删除")
    assert write.risk == "HIGH_RISK"
    negative = classifier.classify("我不想删除订单，只想知道影响")
    assert negative.risk == "READ_ONLY"
    assert negative.negative_action is True
    composite = classifier.classify("分析库存风险并查询公司的补货制度")
    assert composite.complexity == "MULTI_DOMAIN"


@pytest.mark.asyncio
async def test_hybrid_selector_is_catalog_driven_and_supports_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "skill_selector_mode", "HYBRID")
    monkeypatch.setattr(settings, "skill_selector_rule_threshold", 0.35)
    selector = SkillSelector()
    generic = await selector.select("研究供应商交期和采购风险", _catalog())
    assert generic.selected is not None
    assert generic.selected.skill_key == "supplier-risk"
    explicit = await selector.select("请处理这个任务", _catalog(), explicit_skill_key="supplier-risk")
    assert explicit.method == "EXPLICIT"
    assert explicit.confidence == 1
    with pytest.raises(AppError, match="无权运行"):
        await selector.select("请处理", _catalog(), explicit_skill_key="not-authorized")


@pytest.mark.asyncio
async def test_hybrid_selector_multi_no_skill_and_negation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "skill_selector_mode", "HYBRID")
    monkeypatch.setattr(settings, "skill_multi_enabled", True)
    monkeypatch.setattr(settings, "skill_selector_semantic_threshold", 0.08)
    monkeypatch.setattr(settings, "skill_selector_rule_threshold", 0.95)
    selection = await SkillSelector().select(
        "分析 SKU-001 最近30天库存风险，并查询知识库 7 的补货制度",
        _catalog(),
    )
    assert {item.skill_key for item in selection.selected_skills} >= {
        "inventory-analysis",
        "knowledge-research",
    }
    assert (await SkillSelector().select("你好", _catalog())).method == "NO_SKILL"
    assert not (await SkillSelector().select("我不想删除订单", _catalog())).selected_skills


class _SelectorAdapter:
    async def stream(
        self,
        messages: list[ModelMessage],
        *,
        tools: list[ModelToolDefinition] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[ChatDelta]:
        del messages, tools, tool_choice
        yield ChatDelta(
            text='{"selected_skill_keys":["knowledge-research"],"confidence":0.91,"reason":"制度查询"}'
        )
        yield ChatDelta(
            finished=True,
            usage={"prompt_tokens": 12, "completion_tokens": 5},
        )


@pytest.mark.asyncio
async def test_llm_selector_output_is_schema_and_candidate_constrained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "skill_selector_mode", "HYBRID")
    monkeypatch.setattr(settings, "skill_selector_llm_enabled", True)
    monkeypatch.setattr(settings, "skill_selector_rule_threshold", 0.99)
    monkeypatch.setattr(settings, "skill_selector_semantic_threshold", 0.01)
    monkeypatch.setattr(settings, "skill_selector_ambiguity_margin", 0.99)
    result = await SkillSelector().select(
        "研究库存制度和订单制度",
        _catalog(),
        adapter=_SelectorAdapter(),  # type: ignore[arg-type]
    )
    assert result.method == "LLM"
    assert result.selected is not None
    assert result.selected.skill_key == "knowledge-research"
    assert result.llm_usage == {"prompt_tokens": 12, "completion_tokens": 5}


def test_input_collector_preserves_confirmed_fields_and_supports_correction() -> None:
    schema = {
        "type": "object",
        "properties": {
            "sku_code": {"type": "string", "description": "SKU"},
            "start_date": {"type": "string", "format": "date"},
            "end_date": {"type": "string", "format": "date"},
        },
        "required": ["sku_code", "start_date", "end_date"],
    }
    collector = SkillInputCollector()
    first = collector.collect("分析 SKU-001 库存风险", schema, today=date(2026, 11, 19))
    assert first.values == {"sku_code": "SKU-001"}
    assert first.missing == ("start_date", "end_date")
    second = collector.collect("最近30天", schema, first.values, today=date(2026, 11, 19))
    assert second.ready
    assert second.values["sku_code"] == "SKU-001"
    assert second.values["start_date"] == "2026-10-21"
    corrected = collector.collect("改成 SKU-002 最近7天", schema, second.values, today=date(2026, 11, 19))
    assert corrected.values["sku_code"] == "SKU-002"
    assert corrected.values["start_date"] == "2026-11-13"
    assert collector.cancelled("取消")


def test_plan_topology_supports_parallel_layers_and_rejects_cycles() -> None:
    levels = _topological_levels(
        {"sales", "inventory", "knowledge"},
        {"sales": [], "inventory": ["sales"], "knowledge": []},
    )
    assert levels == [["knowledge", "sales"], ["inventory"]]
    with pytest.raises(AppError, match="循环"):
        _topological_levels({"a", "b"}, {"a": ["b"], "b": ["a"]})
    with pytest.raises(AppError, match="未包含"):
        _topological_levels({"a"}, {"a": ["missing"]})


def test_skill_evaluation_metrics_and_hundred_case_catalog() -> None:
    case = {
        "expected_behavior": {
            "expected_skill_keys": ["inventory-analysis", "knowledge-research"],
            "expected_plan_steps": 2,
        },
        "expected_tools": {"required": [], "optional": [], "forbidden": []},
    }
    result = {
        "transport_success": True,
        "agent_completed": True,
        "selected_skill_keys": ["inventory-analysis", "knowledge-research"],
        "selection_method": "LEXICAL",
        "plan_valid": True,
        "plan_steps": 2,
        "multi_skill_success": True,
        "dependency_success_rate": 1.0,
    }
    outcome, metrics, assertions = evaluate_case(case, result)
    assert outcome == "TASK_SUCCESS"
    assert metrics["selection_accuracy"] is True
    assert metrics["plan_validity"] is True
    aggregate = aggregate_metrics([{"task_outcome": outcome, "metrics": metrics}])
    assert aggregate["multi_skill_task_success_rate"]["value"] == 1
    bases = AgentEvaluationService._v14_skill_case_bases()
    assert len(bases) == 30
    inventory_profiles = bases[0]["scenario_config"]["replay_by_profile"]
    assert inventory_profiles["BASELINE"]["selected_skill_keys"] == []
    assert inventory_profiles["HYBRID"]["selected_skill_keys"] == ["inventory-analysis"]
    multi_profiles = bases[6]["scenario_config"]["replay_by_profile"]
    assert multi_profiles["BASIC"]["selected_skill_keys"] == ["inventory-analysis"]
    assert multi_profiles["HYBRID"]["selected_skill_keys"] == [
        "inventory-analysis",
        "knowledge-research",
    ]


def test_skill_evaluation_run_config_is_strict_and_version_comparable() -> None:
    payload = EvaluationRunCreate(
        dataset_version_id=1,
        mode="AUTO",
        idempotency_key="evaluation-config-1",
        config={
            "selector_profile": "HYBRID",
            "skill_version_overrides": {"inventory-analysis": 2},
            "skill_enabled": True,
        },
    )
    assert payload.config["selector_profile"] == "HYBRID"
    with pytest.raises(ValueError):
        EvaluationRunCreate(
            dataset_version_id=1,
            mode="AUTO",
            idempotency_key="evaluation-config-2",
            config={"arbitrary_prompt": "unsafe"},
        )
