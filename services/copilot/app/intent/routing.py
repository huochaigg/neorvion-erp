"""把理解结果翻译成对现有 AgentRouter / SkillSelector 的约束，而不是再猜一遍。"""

from __future__ import annotations

from typing import Literal

from app.intent.registry import ANALYSIS_SKILLS
from app.intent.schemas import IntentDecision, ResolvedTask, RoutingPlan

AgentMode = Literal["single", "multi", "workflow"]

_QUERY_TYPES = {"QUERY", "GUIDE", "CHAT"}


class RoutingPlanner:
    """
    输入：任务计划与裁决状态。
    输出：Agent 模式、Skill 策略和是否追问。
    流程：多任务优先保留 Multi-Agent；分析 Skill 不得截断普通查询。
    边界：显式 Skill 仍由调用方传入，但这里会给出 forbid 列表供执行层复核。
    """

    def plan(
        self,
        tasks: tuple[ResolvedTask, ...],
        *,
        decision: IntentDecision,
        skill_mode: str = "AUTO",
        explicit_skill_key: str | None = None,
    ) -> RoutingPlan:
        if decision in {"AMBIGUOUS", "INSUFFICIENT"} and self._needs_clarify(tasks, decision):
            return RoutingPlan(
                agent_mode="single",
                agents=self._agents(tasks)[:1],
                skill_policy="SKIP",
                allow_multi_agent=False,
                clarify=True,
                pending=decision == "INSUFFICIENT" and any(task.problem_type == "ACTION" for task in tasks),
                reason="需要澄清或补参，不进入自动 Skill / 写路径",
            )
        agents = self._agents(tasks)
        mode = self._mode(tasks, agents)
        if skill_mode == "NONE":
            return RoutingPlan(
                agent_mode=mode,
                agents=agents,
                skill_policy="SKIP",
                allow_multi_agent=mode == "multi",
                reason="用户本轮选择普通对话",
            )
        if skill_mode == "MANUAL" and explicit_skill_key:
            return RoutingPlan(
                agent_mode="single",
                agents=agents[:1],
                skill_policy="EXPLICIT",
                skill_keys=(explicit_skill_key,),
                allow_multi_agent=False,
                reason="显式 Skill 优先，但仍受权限和执行安全限制",
            )
        skill_keys, forbid = self._skills(tasks)
        if len(tasks) > 1 and skill_keys:
            uncovered = [
                task
                for task in tasks
                if task.candidate_skills and not set(task.candidate_skills) & set(skill_keys)
            ]
            if uncovered or len(skill_keys) < len(
                [task for task in tasks if task.candidate_skills]
            ):
                return RoutingPlan(
                    agent_mode="multi" if len(agents) >= 2 else mode,
                    agents=agents,
                    skill_policy="SKIP",
                    forbid_skill_keys=tuple(ANALYSIS_SKILLS),
                    allow_multi_agent=len(agents) >= 2,
                    reason="多任务不能被单个 Skill 截断，改走 Agent 编排",
                )
            if len(skill_keys) > 1:
                return RoutingPlan(
                    agent_mode="multi",
                    agents=agents,
                    skill_policy="MULTI",
                    skill_keys=skill_keys,
                    allow_multi_agent=True,
                    reason="多个互补 Skill 覆盖任务计划",
                )
        if skill_keys:
            return RoutingPlan(
                agent_mode="single",
                agents=agents[:1] or (),
                skill_policy="CANDIDATE",
                skill_keys=skill_keys[:1],
                forbid_skill_keys=forbid,
                allow_multi_agent=False,
                reason="分析型任务命中已登记 Skill 候选",
            )
        return RoutingPlan(
            agent_mode=mode,
            agents=agents,
            skill_policy="SKIP",
            forbid_skill_keys=tuple(ANALYSIS_SKILLS) if self._has_plain_query(tasks) else forbid,
            allow_multi_agent=mode == "multi",
            reason="普通查询/教学走 Agent，不自动选择分析 Skill",
        )

    def _needs_clarify(self, tasks: tuple[ResolvedTask, ...], decision: IntentDecision) -> bool:
        if decision == "AMBIGUOUS":
            return True
        if decision != "INSUFFICIENT":
            return False
        return any(
            (task.problem_type == "ACTION" and task.missing_slots)
            or (task.problem_type == "ANALYZE" and task.missing_slots)
            or (
                task.intent_key
                in {"product.price_query", "product.price_change", "sales.order_query"}
                and not task.slots
            )
            for task in tasks
        )

    @staticmethod
    def _agents(tasks: tuple[ResolvedTask, ...]) -> tuple[str, ...]:
        names: list[str] = []
        for task in tasks:
            preferred = task.candidate_agents[:1]
            if task.problem_type == "GUIDE" and "knowledge_agent" in task.candidate_agents:
                preferred = ("knowledge_agent",)
            for agent in preferred:
                if agent not in names and agent != "supervisor_agent":
                    names.append(agent)
        return tuple(names)

    @staticmethod
    def _mode(tasks: tuple[ResolvedTask, ...], agents: tuple[str, ...]) -> AgentMode:
        if all(task.problem_type in {"GUIDE", "CHAT"} for task in tasks):
            return "single"
        if any(task.intent_key == "procurement.create_draft" for task in tasks) and len(tasks) == 1:
            return "workflow"
        if len(tasks) >= 2 and len(agents) >= 2:
            return "multi"
        if len(tasks) >= 2 and {task.domain for task in tasks} != {tasks[0].domain}:
            return "multi"
        return "single"

    def _skills(self, tasks: tuple[ResolvedTask, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        selected: list[str] = []
        forbid = list(ANALYSIS_SKILLS)
        for task in tasks:
            if task.problem_type in _QUERY_TYPES:
                continue
            if task.problem_type != "ANALYZE":
                continue
            if task.missing_slots and task.intent_key.startswith("inventory."):
                continue
            for key in task.candidate_skills:
                if key not in selected:
                    selected.append(key)
                if key in forbid:
                    forbid.remove(key)
        return tuple(selected), tuple(forbid)

    @staticmethod
    def _has_plain_query(tasks: tuple[ResolvedTask, ...]) -> bool:
        return any(task.problem_type == "QUERY" for task in tasks)
