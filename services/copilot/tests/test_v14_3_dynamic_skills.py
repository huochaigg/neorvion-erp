from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.graph.workflow import AgentRuntime
from app.schemas.chat import ChatRequest
from app.services.evaluations import SelectorLiveEvaluationRunner
from app.skills.catalog import SkillCatalog, SkillCatalogEntry, SkillCatalogSnapshot
from app.skills.chat import prepare_chat_skill
from app.skills.parser import SkillParser
from app.skills.selector import SkillSelector

FIXTURES = Path(__file__).parent / "fixtures" / "skills"


def _context() -> TenantContext:
    return TenantContext(
        user_id=33,
        tenant_id=7,
        member_id=330,
        is_owner=False,
        role="USER",
        role_codes=("USER",),
        permission_codes=frozenset(
            {
                "copilot:use",
                "copilot:skill:run",
                "inventory:read",
                "analytics:sales:read",
                "order:read",
            }
        ),
        token_jti="v14-3",
        token_version=1,
        authz_version=1,
    )


def test_dynamic_fixture_packages_are_real_standard_skill_packages() -> None:
    for key in ("inventory-coverage-summary", "order-status-explanation"):
        root = FIXTURES / key
        definition = SkillParser().parse_directory(root)
        assert definition.name == key
        assert definition.resources
        assert (root / "governance.json").is_file()
        assert "不得" in definition.instructions


@pytest.mark.asyncio
async def test_dynamic_skill_needs_no_selector_code_and_supports_manual_at_and_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "skill_selector_mode", "HYBRID")
    monkeypatch.setattr(settings, "skill_selector_rule_threshold", 0.99)
    monkeypatch.setattr(settings, "skill_selector_semantic_threshold", 0.05)
    dynamic = SkillCatalogEntry(
        91,
        901,
        "inventory-coverage-summary",
        "库存覆盖天数摘要",
        "解释精确 SKU 在明确日期范围内已计算的覆盖天数，不执行广义风险诊断",
        1,
        {"metadata": {"neorvion-category": "inventory-summary"}},
    )
    selector = SkillSelector()
    assert (await selector.select("给我一份 SKU-001 覆盖天数摘要", [])).method == "NO_SKILL"
    automatic = await selector.select("给我一份 SKU-001 覆盖天数摘要", [dynamic])
    assert automatic.selected is dynamic
    assert automatic.method == "LEXICAL"
    manual = await selector.select("开始处理", [dynamic], explicit_skill_key=dynamic.skill_key)
    assert manual.method == "EXPLICIT"
    at_skill = await selector.select("@inventory-coverage-summary 分析 SKU-001", [dynamic])
    assert at_skill.method == "EXPLICIT"
    with pytest.raises(AppError, match="不一致"):
        await selector.select(
            "@inventory-coverage-summary 分析",
            [dynamic, SkillCatalogEntry(92, 902, "order-status-explanation", "订单状态解释", "解释订单状态", 1)],
            explicit_skill_key="order-status-explanation",
        )
    assert (await selector.select("解释 inventory-coverage-summary 是什么", [dynamic])).method != "EXPLICIT"


@pytest.mark.asyncio
async def test_none_mode_skips_catalog_even_when_chat_skill_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    result = await prepare_chat_skill(
        SimpleNamespace(),  # type: ignore[arg-type]
        _context(),
        "不要使用任何 Skill，直接回答我",
        "request-none",
        AgentRuntime(),
        conversation_id=None,
        message_id=None,
        skill_mode="NONE",
    )
    assert result is None


def test_chat_skill_picker_contract_is_strict_and_backward_compatible() -> None:
    manual = ChatRequest(
        messages=[{"role": "user", "content": "分析库存"}],
        skill_mode="MANUAL",
        skill_key="inventory-analysis",
    )
    assert manual.skill_mode == "MANUAL"
    legacy = ChatRequest(
        messages=[{"role": "user", "content": "分析库存"}],
        skill_key="inventory-analysis",
    )
    assert legacy.skill_mode == "MANUAL"
    with pytest.raises(ValueError):
        ChatRequest(messages=[{"role": "user", "content": "分析库存"}], skill_mode="MANUAL")
    with pytest.raises(ValueError):
        ChatRequest(
            messages=[{"role": "user", "content": "分析库存"}],
            skill_mode="NONE",
            skill_key="inventory-analysis",
        )


@pytest.mark.asyncio
async def test_five_hundred_skill_catalog_keeps_top_k_and_metadata_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "skill_selector_mode", "HYBRID")
    catalog = [
        SkillCatalogEntry(
            index,
            index + 1000,
            f"business-skill-{index}",
            f"业务技能 {index}",
            f"处理业务领域 {index} 的只读摘要",
            1,
            {"aliases": [f"领域{index}"]},
        )
        for index in range(1, 501)
    ]
    result = await SkillSelector(top_k=5, recall_threshold=0.01).select(
        "请处理业务领域 377 的只读摘要",
        catalog,
    )
    assert len(result.candidates) <= 5
    assert any(item.skill_key == "business-skill-377" for item in result.candidates)
    assert all(not hasattr(item, "instructions") for item in catalog)


@pytest.mark.asyncio
async def test_selector_live_evaluation_runs_real_catalog_and_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = SkillCatalogEntry(
        91,
        901,
        "inventory-coverage-summary",
        "库存覆盖天数摘要",
        "生成精确 SKU 的覆盖天数摘要",
        1,
    )

    async def snapshot(_self) -> SkillCatalogSnapshot:
        return SkillCatalogSnapshot((entry,), 1.25, 1, {})

    monkeypatch.setattr(SkillCatalog, "snapshot", snapshot)
    monkeypatch.setattr(settings, "skill_selector_mode", "HYBRID")
    run = SimpleNamespace(
        id=8,
        tenant_id=7,
        user_id=33,
        config_snapshot={
            "selector_profile": "HYBRID",
            "evaluation_permission_codes": list(_context().permission_codes),
        },
    )
    result = await SelectorLiveEvaluationRunner(
        SimpleNamespace(), 7, 33, "test"  # type: ignore[arg-type]
    ).case_result(
        run,  # type: ignore[arg-type]
        {
            "user_input": "生成 SKU-001 的覆盖天数摘要",
            "expected_behavior": {
                "expected_skill_keys": ["inventory-coverage-summary"]
            },
        },
    )
    assert result is not None
    assert result["selected_skill_keys"] == ["inventory-coverage-summary"]
    assert result["selection_method"] in {"RULE", "LEXICAL"}
    assert result["tool_calls"] == []
    assert result["catalog_latency_ms"] == 1.25
