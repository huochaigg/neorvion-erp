from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.graph.workflow import AgentRuntime
from app.models.ecosystem import Skill, SkillRun, SkillVersion
from app.services.ecosystem import EcosystemService
from app.skills.catalog import SkillCatalog, SkillCatalogEntry
from app.skills.chat import ChatSkillSession, _extract_input, prepare_chat_skill
from app.skills.classification import TaskClassifier
from app.skills.loader import LoadedSkill, SkillRuntimeLoader
from app.skills.parser import SkillParser
from app.skills.selector import SkillSelection, SkillSelector
from app.tools.executor import ToolRuntime


def _context() -> TenantContext:
    return TenantContext(
        user_id=42,
        tenant_id=7,
        member_id=70,
        is_owner=False,
        role="USER",
        role_codes=("USER",),
        permission_codes=frozenset(
            {"copilot:skill:run", "inventory:read", "analytics:sales:read"}
        ),
        token_jti="skill-test",
        token_version=1,
        authz_version=1,
    )


def _models() -> tuple[Skill, SkillVersion]:
    skill = Skill(
        id=10,
        tenant_id=7,
        skill_key="inventory-analysis",
        name="inventory-analysis",
        description="inventory",
        current_version=1,
        enabled=True,
        approval_status="APPROVED",
        created_by=42,
        updated_by=42,
    )
    version = SkillVersion(
        id=20,
        tenant_id=7,
        skill_id=10,
        version=1,
        instructions="只使用确定性 ERP Tool 分析库存覆盖并输出 JSON。",
        input_schema={
            "type": "object",
            "properties": {
                "sku_code": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["sku_code", "start_date", "end_date"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "coverage_days": {"type": "number"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "coverage_days", "evidence_refs"],
        },
        allowed_agents=["inventory_agent"],
        required_permissions=["inventory:read", "analytics:sales:read"],
        allowed_tools=["analyze_inventory_coverage"],
        required_evidence=True,
        risk_level="READ_ONLY",
        timeout_seconds=30,
        token_budget=3000,
        source_format="SKILL_MD",
        source_metadata={
            "name": "inventory-analysis",
            "description": "inventory",
            "metadata": {"neorvion-resource-triggers": "风险,risk"},
        },
        resources={"references/inventory-rules.md": "仅解释 Tool 已计算的覆盖天数。"},
        content_hash="a" * 64,
        approval_status="APPROVED",
        created_by=42,
        created_at=datetime.now(UTC),
    )
    return skill, version


def test_builtin_skill_files_follow_open_format() -> None:
    root = Path(__file__).resolve().parents[1] / "skills"
    for key in ("inventory-analysis", "sales-order-review", "knowledge-research"):
        definition = SkillParser().parse_directory(root / key)
        assert definition.name == key
        assert definition.instructions
        assert definition.resources


@pytest.mark.parametrize(
    "body",
    [
        "# no frontmatter",
        "---\ndescription: missing name\n---\nbody",
        "---\nname: Wrong_Name\ndescription: invalid\n---\nbody",
        "---\nname: demo\ndescription: x\nmetadata: !!python/object {}\n---\nbody",
    ],
)
def test_parser_rejects_invalid_frontmatter(tmp_path: Path, body: str) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    (root / "SKILL.md").write_text(body, "utf-8")
    with pytest.raises(AppError):
        SkillParser().parse_directory(root)


def test_parser_rejects_missing_or_escaping_reference(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill for tests.\n---\nSee references/missing.md",
        "utf-8",
    )
    with pytest.raises(AppError):
        SkillParser().parse_directory(root)


def test_parser_rejects_deep_reference_and_oversized_skill(tmp_path: Path) -> None:
    deep = tmp_path / "deep"
    deep.mkdir()
    (deep / "SKILL.md").write_text(
        "---\nname: deep\ndescription: Deep reference test.\n---\nSee references/a/b.md",
        "utf-8",
    )
    with pytest.raises(AppError, match="路径非法"):
        SkillParser().parse_directory(deep)
    large = tmp_path / "large"
    large.mkdir()
    (large / "SKILL.md").write_text(
        "---\nname: large\ndescription: Large skill test.\n---\n" + ("x" * 70_000),
        "utf-8",
    )
    with pytest.raises(AppError, match="大小限制"):
        SkillParser().parse_directory(large)


@pytest.mark.asyncio
async def test_package_import_rejects_zip_slip_before_database_access() -> None:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("demo/../SKILL.md", "unsafe")
        archive.writestr("demo/governance.json", "{}")
    service = EcosystemService(SimpleNamespace(), _context())  # type: ignore[arg-type]
    with pytest.raises(AppError, match="不安全"):
        await service.import_skill_package(content.getvalue())


@pytest.mark.asyncio
async def test_selector_is_conservative_and_supports_no_skill() -> None:
    catalog = [
        SkillCatalogEntry(1, 11, "inventory-analysis", "库存", "库存覆盖", 1),
        SkillCatalogEntry(2, 22, "sales-order-review", "销售", "销售订单审查", 1),
        SkillCatalogEntry(3, 33, "knowledge-research", "知识", "制度研究", 1),
    ]
    selector = SkillSelector()
    assert (await selector.select("分析 SKU-001 的库存覆盖天数", catalog)).selected.skill_key == "inventory-analysis"
    assert (await selector.select("审查销售订单 SO-001", catalog)).selected.skill_key == "sales-order-review"
    assert (await selector.select("查一下公司的退货制度", catalog)).selected.skill_key == "knowledge-research"
    assert (await selector.select("你好", catalog)).method == "NO_SKILL"
    assert (await selector.select("我不想删除订单", catalog)).selected is None


def test_inventory_relative_date_is_deterministic_and_never_model_guessed() -> None:
    value = _extract_input("inventory-analysis", "分析 SKU-001 最近30天库存风险")
    assert value["sku_code"] == "SKU-001"
    start = datetime.fromisoformat(value["start_date"]).date()
    end = datetime.fromisoformat(value["end_date"]).date()
    assert (end - start).days == 29


@pytest.mark.asyncio
async def test_feature_flag_off_keeps_old_chat_without_touching_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "skill_chat_enabled", False)
    assert (
        await prepare_chat_skill(
            SimpleNamespace(),  # type: ignore[arg-type]
            _context(),
            "分析 SKU-001 库存覆盖",
            "request-id",
            AgentRuntime(),
            conversation_id=None,
            message_id=None,
        )
        is None
    )


@pytest.mark.asyncio
async def test_no_skill_falls_back_to_old_chat_when_flag_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def empty_catalog(_self) -> list[SkillCatalogEntry]:
        return []

    monkeypatch.setattr(settings, "skill_chat_enabled", True)
    monkeypatch.setattr(SkillCatalog, "available", empty_catalog)
    assert (
        await prepare_chat_skill(
            SimpleNamespace(),  # type: ignore[arg-type]
            _context(),
            "你好",
            "request-id",
            AgentRuntime(),
            conversation_id=None,
            message_id=None,
        )
        is None
    )


class _LoaderSession:
    def __init__(self, row) -> None:
        self.row = row

    async def execute(self, _statement):
        return SimpleNamespace(first=lambda: self.row)


@pytest.mark.asyncio
async def test_loader_progressively_loads_only_selected_instructions_and_needed_resource() -> None:
    skill, version = _models()
    loader = SkillRuntimeLoader(_LoaderSession((skill, version)), _context())  # type: ignore[arg-type]
    entry = SkillCatalogEntry(10, 20, skill.skill_key, skill.name, skill.description, 1)
    loaded = await loader.load(entry, "分析 SKU-001 库存风险")
    assert loaded.version.id == 20
    assert list(loaded.loaded_resources) == ["references/inventory-rules.md"]
    metadata_only = await loader.load(entry, "分析 SKU-001 库存覆盖")
    assert metadata_only.loaded_resources == {}
    with pytest.raises(AppError):
        loader.read_resource(version, "../other/SKILL.md")


class _CommitSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_chat_skill_session_binds_agent_tools_validates_output_and_evidence() -> None:
    skill, version = _models()
    row = SkillRun(
        id=30,
        tenant_id=7,
        skill_id=10,
        skill_version=1,
        user_id=42,
        idempotency_key="chat:test",
        status="RUNNING",
        input_snapshot={},
        output_snapshot={},
    )
    database = _CommitSession()
    session = ChatSkillSession(
        database,  # type: ignore[arg-type]
        LoadedSkill(skill, version, {"references/inventory-rules.md": "只解释，不授权。"}),
        SkillSelection(
            (SkillCatalogEntry(10, 20, skill.skill_key, skill.name, skill.description, 1),),
            "DETERMINISTIC_RULE",
            "matched",
            1.0,
            TaskClassifier().classify("库存分析"),
        ),
        row,
        {"sku_code": "SKU-001", "start_date": "2026-10-01", "end_date": "2026-10-31"},
    )
    tools = ToolRuntime(
        tenant=_context(),
        access_token="token",
        erp_audience_authorized=True,
        allowed_tools=frozenset({"analyze_inventory_coverage", "get_sales_order"}),
    )
    runtime = AgentRuntime(tools=tools)
    session.apply_runtime(runtime)
    assert runtime.agent_name == "inventory_agent"
    assert tools.allowed_tools == frozenset({"analyze_inventory_coverage"})
    messages = session.messages([{"role": "user", "content": "原始任务"}])
    assert "<untrusted_skill_instructions>" in messages[-1]["content"]
    assert "untrusted_skill_resource" in messages[-1]["content"]
    tools.evidences.append(
        {
            "citation_id": "E1",
            "source_type": "ERP",
            "tool_call_id": "call-1",
            "resource_type": "analyze_inventory_coverage",
            "observed_at": datetime.now(UTC).isoformat(),
        }
    )
    await session.complete(
        '{"summary":"ok [E1]","coverage_days":8.4,"evidence_refs":["E1"]}',
        {"prompt_tokens": 10, "completion_tokens": 5},
        runtime,
    )
    assert row.status == "SUCCEEDED"
    assert row.output_snapshot["result"]["coverage_days"] == 8.4
    assert database.commits == 1
