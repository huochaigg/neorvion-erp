"""工具可用性策略。分类与路由都不授予权限，写操作默认 fail-closed。"""

from __future__ import annotations

from app.intent.registry import WRITE_TOOLS
from app.intent.schemas import IntentDecision, ResolvedTask, ToolPolicy


class ToolAvailabilityPolicy:
    """
    输入：已裁决任务。
    输出：服务端工具约束。
    边界：GUIDE/CHAT/否定执行/未知/未实现 ACTION 都不得打开 propose_action。
    """

    def build(
        self,
        tasks: tuple[ResolvedTask, ...],
        *,
        decision: IntentDecision,
        negative_action: bool,
        has_open_proposal: bool,
    ) -> ToolPolicy:
        if negative_action:
            return ToolPolicy(
                allow_propose_action=False,
                blocked_tools=tuple(WRITE_TOOLS),
                reason="否定执行或仅询问，服务端禁止自动创建草稿",
            )
        if decision in {"AMBIGUOUS", "UNKNOWN"}:
            return ToolPolicy(
                allow_propose_action=False,
                blocked_tools=tuple(WRITE_TOOLS),
                reason="分类不确定时禁止写工具",
            )
        if decision == "INSUFFICIENT":
            return ToolPolicy(
                allow_propose_action=False,
                blocked_tools=tuple(WRITE_TOOLS),
                reason="关键参数不足，不能把追问当成已批准",
            )
        write_tasks = [
            task
            for task in tasks
            if task.problem_type == "ACTION" and task.executable and "propose_action" in task.capability_hints
        ]
        if any(task.problem_type == "GUIDE" for task in tasks) and not write_tasks:
            return ToolPolicy(
                allow_propose_action=False,
                blocked_tools=tuple(WRITE_TOOLS),
                reason="操作教学不得进入执行链",
            )
        if any(not task.executable and task.problem_type == "ACTION" for task in tasks):
            return ToolPolicy(
                allow_propose_action=False,
                blocked_tools=tuple(WRITE_TOOLS),
                reason="已识别但没有对应执行工具",
            )
        if write_tasks and all(not task.missing_slots for task in write_tasks):
            return ToolPolicy(
                allow_propose_action=True,
                blocked_tools=(),
                reason="存在可草稿化的 ACTION；真实写入仍须 Proposal/确认",
            )
        if has_open_proposal:
            return ToolPolicy(
                allow_propose_action=False,
                blocked_tools=tuple(WRITE_TOOLS),
                reason="已有待确认草稿，不能因新分类再开写工具",
            )
        return ToolPolicy(
            allow_propose_action=False,
            blocked_tools=tuple(WRITE_TOOLS),
            reason="默认禁止因意图识别扩大写权限",
        )
