from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import build_agent_registry
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.graph.workflow import AgentRuntime
from app.models.ecosystem import (
    SkillExecutionPlan,
    SkillExecutionPlanStep,
    SkillRun,
)
from app.services.skill_execution import SkillExecutionService
from app.skills.inputs import SkillInputCollector
from app.skills.loader import LoadedSkill, SkillRuntimeLoader
from app.skills.selector import SkillSelection


@dataclass(slots=True)
class PlannedSkill:
    loaded: LoadedSkill
    input: dict[str, Any]
    run: SkillRun
    step: SkillExecutionPlanStep


@dataclass(slots=True)
class MultiSkillChatSession:
    """把受控 Skill Plan 交给原 MultiAgentWorkflow；自身只负责边界、状态与校验。"""

    db: AsyncSession
    plan: SkillExecutionPlan
    items: list[PlannedSkill]
    selection: SkillSelection
    agent_groups: list[list[tuple[str, str]]]

    @property
    def timeout_seconds(self) -> float:
        return min(
            settings.skill_plan_timeout_seconds,
            sum(item.loaded.version.timeout_seconds for item in self.items),
        )

    @property
    def public_data(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan.id,
            "status": self.plan.status,
            "selection_method": self.selection.method,
            "selection_reason": self.selection.reason,
            "confidence": self.selection.confidence,
            "skills": [
                {
                    "skill_id": item.loaded.skill.id,
                    "skill_run_id": item.run.id,
                    "skill_version_id": item.loaded.version.id,
                    "skill_key": item.loaded.skill.skill_key,
                    "skill_name": item.loaded.skill.name,
                    "step_key": item.step.step_key,
                    "status": item.run.status,
                }
                for item in self.items
            ],
        }

    def apply_runtime(self, runtime: AgentRuntime) -> None:
        if runtime.tools is None:
            raise AppError("Skill Plan Tool Runtime 不可用", code=50087, status_code=500)
        registry = build_agent_registry()
        tools: set[str] = set()
        agents: set[str] = set()
        model_calls = 1
        for item in self.items:
            version = item.loaded.version
            agent_name = version.allowed_agents[0]
            spec = registry.get(agent_name)
            if not set(version.allowed_tools).issubset(spec.allowed_tools):
                raise AppError("Skill Plan 的 Agent 与 Tool 不兼容", code=40986, status_code=409)
            tools.update(version.allowed_tools)
            agents.add(agent_name)
            model_calls += spec.max_model_calls
        governed = runtime.tools.allowed_tools
        if governed is not None and not tools.issubset(governed):
            raise AppError("Skill Plan 工具不符合租户治理策略", code=40377, status_code=403)
        runtime.tools.allowed_tools = frozenset(tools)
        runtime.tools.max_calls_override = min(settings.tool_max_calls, sum(len(item.loaded.version.allowed_tools) * 2 for item in self.items))
        runtime.tools.global_call_limit = runtime.tools.max_calls_override
        runtime.allow_multi_agent = True
        runtime.agent_name = None
        runtime.agent_task_id = f"skill-plan-{self.plan.id}"
        runtime.agent_results = []
        runtime.skill_agent_groups = self.agent_groups
        runtime.max_model_calls = min(settings.budget_max_model_calls_per_request, model_calls)

    def messages(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blocks = []
        for item in self.items:
            resources = "".join(
                f'\n<untrusted_skill_resource skill="{item.loaded.skill.skill_key}" path="{path}">{content}</untrusted_skill_resource>'
                for path, content in item.loaded.loaded_resources.items()
            )
            blocks.append(
                f'<skill_plan_step key="{item.step.step_key}" agent="{item.step.agent_name}">\n'
                + SkillExecutionService._message(item.loaded.version, item.input)
                + resources
                + "\n</skill_plan_step>"
            )
        instruction = (
            "这是已由服务端验证的只读多 Skill 计划。专业 Agent 只处理与自己授权匹配的步骤，"
            "Supervisor 只能汇总真实专业结果和 Evidence，不得扩展工具、权限或步骤。\n"
            + "\n".join(blocks)
        )
        return [*history, {"role": "user", "content": instruction}]

    def lifecycle_events(self) -> list[dict[str, Any]]:
        events = [{"event": "skill_plan_created", "data": self.public_data}]
        for item in self.items:
            events.append(
                {
                    "event": "skill_selected",
                    "data": {
                        "plan_id": self.plan.id,
                        "skill_id": item.loaded.skill.id,
                        "skill_run_id": item.run.id,
                        "skill_version_id": item.loaded.version.id,
                        "skill_key": item.loaded.skill.skill_key,
                        "skill_name": item.loaded.skill.name,
                        "step_key": item.step.step_key,
                        "selection_method": self.selection.method,
                    },
                }
            )
            events.append(
                {
                    "event": "skill_start",
                    "data": {
                        "plan_id": self.plan.id,
                        "skill_id": item.loaded.skill.id,
                        "skill_run_id": item.run.id,
                        "skill_version_id": item.loaded.version.id,
                        "skill_key": item.loaded.skill.skill_key,
                        "skill_name": item.loaded.skill.name,
                        "step_key": item.step.step_key,
                        "selection_method": self.selection.method,
                        "selection_reason": self.selection.reason,
                        "status": item.run.status,
                    },
                }
            )
            for path in item.loaded.loaded_resources:
                events.append(
                    {
                        "event": "skill_resource_loaded",
                        "data": {
                            "plan_id": self.plan.id,
                            "step_key": item.step.step_key,
                            "resource_path": path,
                            "resource_metrics": item.loaded.resource_metrics.get(path, {}),
                        },
                    }
                )
        return events

    def record_agent_event(self, event: str, data: dict[str, Any]) -> None:
        """把现有 Multi-Agent task 生命周期映射到 Plan Step，不复制 Trace 表。"""
        task_id = str(data.get("agent_task_id") or "")
        item = next((row for row in self.items if row.step.step_key == task_id), None)
        if item is None:
            return
        now = datetime.now(UTC)
        if event == "agent_start" and item.step.status == "PENDING":
            item.step.status = "RUNNING"
            item.step.started_at = now
            item.run.status = "RUNNING"
            item.run.started_at = now
        elif event == "agent_error":
            item.step.status = "FAILED"
            item.step.safe_error = "专业 Agent 执行失败"
            item.step.finished_at = now

    async def complete(self, answer: str, usage: Any, runtime: AgentRuntime, *, commit: bool = True) -> None:
        results = runtime.agent_results or []
        succeeded = 0
        for item in self.items:
            result = next((row for row in results if row.task_id == item.step.step_key), None)
            try:
                if result is None or result.status != "SUCCEEDED" or not result.findings:
                    raise AppError("专业 Agent 未返回可验证结果", code=50289, status_code=502)
                parsed = SkillExecutionService._parse_output(result.findings[0])
                from app.mcp.security import validate_arguments

                validate_arguments(item.loaded.version.output_schema, parsed)
                evidence = SkillExecutionService._valid_evidence(item.loaded.version, result.evidences)
                item.run.status = "SUCCEEDED"
                item.run.output_snapshot = SkillExecutionService._redact(
                    {
                        "result": parsed,
                        "evidence": evidence,
                        "plan_id": self.plan.id,
                        "step_key": item.step.step_key,
                        "loaded_resources": list(item.loaded.loaded_resources),
                        "resource_metrics": item.loaded.resource_metrics,
                    }
                )
                item.step.status = "SUCCEEDED"
                item.step.result_snapshot = SkillExecutionService._redact({"result": parsed, "evidence": evidence})
                succeeded += 1
            except Exception as exc:
                item.run.status = "FAILED"
                item.run.safe_error = exc.message if isinstance(exc, AppError) else "Skill Plan 步骤校验失败"
                item.step.status = "FAILED"
                item.step.safe_error = item.run.safe_error
            item.run.finished_at = datetime.now(UTC)
            item.step.finished_at = datetime.now(UTC)
        self.plan.status = "SUCCEEDED" if succeeded == len(self.items) else "PARTIAL_FAILED" if succeeded else "FAILED"
        self.plan.finished_at = datetime.now(UTC)
        if not succeeded:
            if commit:
                await self.db.commit()
            raise AppError("Skill Plan 所有步骤均失败", code=50289, status_code=502)
        if commit:
            await self.db.commit()

    async def fail(self, exc: BaseException, runtime: AgentRuntime | None = None, *, commit: bool = True) -> None:
        del runtime
        safe = exc.message if isinstance(exc, AppError) else "Skill Plan 执行失败"
        self.plan.status = "CANCELLED" if isinstance(exc, asyncio.CancelledError) else "FAILED"
        self.plan.safe_error = safe
        self.plan.finished_at = datetime.now(UTC)
        for item in self.items:
            if item.run.status in {"CREATED", "RUNNING"}:
                item.run.status = "FAILED"
                item.run.safe_error = safe
                item.run.finished_at = datetime.now(UTC)
            if item.step.status in {"PENDING", "RUNNING"}:
                item.step.status = "CANCELLED" if isinstance(exc, asyncio.CancelledError) else "FAILED"
                item.step.safe_error = safe
                item.step.finished_at = datetime.now(UTC)
        if commit:
            await self.db.commit()


async def prepare_multi_skill(
    db: AsyncSession,
    context: TenantContext,
    selection: SkillSelection,
    task: str,
    request_id: str,
    runtime: AgentRuntime,
    *,
    conversation_id: int | None,
    message_id: int | None,
    collected_inputs: dict[str, dict[str, Any]] | None = None,
) -> MultiSkillChatSession:
    """验证 DAG、总预算、Agent/Tool 和每步输入后，原子创建 Plan、Step 与 SkillRun。"""
    if conversation_id is None or message_id is None:
        raise AppError("多 Skill 计划只支持持久化会话", code=42294, status_code=422)
    if not 2 <= len(selection.selected_skills) <= settings.skill_plan_max_steps:
        raise AppError("Skill Plan 步骤数量非法", code=42294, status_code=422)
    loaded = [await SkillRuntimeLoader(db, context).load(entry, task) for entry in selection.selected_skills]
    by_key = {item.skill.skill_key: item for item in loaded}
    dependencies = {
        key: [str(value) for value in item.version.source_metadata.get("dependencies", [])]
        for key, item in by_key.items()
    }
    levels = _topological_levels(set(by_key), dependencies)
    loaded = [by_key[key] for level in levels for key in level]
    total_tokens = sum(item.version.token_budget for item in loaded)
    if total_tokens > settings.skill_plan_max_total_tokens:
        raise AppError("Skill Plan Token 预算超过上限", code=42979, status_code=429)
    collector = SkillInputCollector()
    inputs: list[dict[str, Any]] = []
    missing: list[str] = []
    for item in loaded:
        result = collector.collect(
            task,
            item.version.input_schema,
            (collected_inputs or {}).get(item.skill.skill_key),
        )
        inputs.append(result.values)
        missing.extend(f"{item.skill.skill_key}.{name}" for name in result.missing)
    if missing:
        raise AppError("多 Skill 计划缺少参数：" + "、".join(missing), code=42291, status_code=422)
    snapshot = {
        "method": selection.method,
        "reason": selection.reason,
        "confidence": selection.confidence,
        "candidates": [{"skill_key": row.skill_key, "score": row.score} for row in selection.candidates],
        "selected_skill_keys": [row.skill.skill_key for row in loaded],
    }
    plan = SkillExecutionPlan(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        idempotency_key=f"plan:{request_id}"[:96],
        status="RUNNING",
        classification=selection.classification.as_dict(),
        selection_snapshot=snapshot,
        budget_snapshot={"token_budget": total_tokens, "timeout_seconds": settings.skill_plan_timeout_seconds, "max_steps": settings.skill_plan_max_steps},
        started_at=datetime.now(UTC),
    )
    db.add(plan)
    await db.flush()
    planned: list[PlannedSkill] = []
    step_keys = {
        item.skill.skill_key: f"step-{position}-{item.skill.skill_key}"[:64]
        for position, item in enumerate(loaded, start=1)
    }
    for position, (item, values) in enumerate(zip(loaded, inputs, strict=True), start=1):
        step_key = step_keys[item.skill.skill_key]
        item_dependencies = dependencies[item.skill.skill_key]
        step = SkillExecutionPlanStep(
            tenant_id=context.tenant_id,
            plan_id=plan.id,
            step_key=step_key,
            position=position,
            skill_id=item.skill.id,
            skill_version_id=item.version.id,
            agent_name=item.version.allowed_agents[0],
            depends_on=[step_keys[value] for value in item_dependencies],
            input_snapshot=SkillExecutionService._redact(values),
            status="PENDING",
        )
        run = SkillRun(
            tenant_id=context.tenant_id,
            skill_id=item.skill.id,
            skill_version=item.version.version,
            user_id=context.user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            selection_method=selection.method,
            selection_snapshot=snapshot,
            plan_id=plan.id,
            plan_step_key=step_key,
            idempotency_key=f"chat:{request_id}:{position}"[:96],
            status="CREATED",
            input_snapshot=SkillExecutionService._redact(values),
        )
        db.add_all([step, run])
        planned.append(PlannedSkill(item, values, run, step))
    await db.commit()
    for item in planned:
        await db.refresh(item.run)
    groups = [
        [(by_key[key].version.allowed_agents[0], step_keys[key]) for key in level]
        for level in levels
    ]
    session = MultiSkillChatSession(db, plan, planned, selection, groups)
    session.apply_runtime(runtime)
    return session


def _topological_levels(
    keys: set[str], dependencies: dict[str, list[str]]
) -> list[list[str]]:
    """返回可并行拓扑层；缺失依赖或循环均在任何执行开始前拒绝。"""
    if any(dependency not in keys for values in dependencies.values() for dependency in values):
        raise AppError("Skill Plan 依赖未包含在已授权候选中", code=42295, status_code=422)
    remaining = set(keys)
    completed: set[str] = set()
    levels: list[list[str]] = []
    while remaining:
        level = sorted(key for key in remaining if set(dependencies.get(key, [])).issubset(completed))
        if not level:
            raise AppError("Skill Plan 存在循环依赖", code=42295, status_code=422)
        levels.append(level)
        completed.update(level)
        remaining.difference_update(level)
    return levels
