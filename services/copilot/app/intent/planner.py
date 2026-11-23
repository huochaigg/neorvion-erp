"""多意图任务规划。保留用户的全部目标，不做复杂 DAG 引擎。"""

from __future__ import annotations

from app.intent.schemas import ResolvedTask

_WRITE_TYPES = {"ACTION"}


class MultiIntentTaskPlanner:
    """
    输入：裁决后的任务列表。
    输出：带顺序、依赖和并行组的任务计划。
    流程：查询/分析可并行；写操作必须串行且不能因缺参被静默丢弃。
    边界：禁止因为单个 Skill 命中就丢掉第二个任务。
    """

    def plan(self, tasks: tuple[ResolvedTask, ...]) -> tuple[ResolvedTask, ...]:
        if len(tasks) <= 1:
            return tasks
        planned: list[ResolvedTask] = []
        previous_write: str | None = None
        group = 0
        for index, task in enumerate(tasks):
            depends: tuple[str, ...] = ()
            if task.problem_type in _WRITE_TYPES:
                group = index
                if previous_write:
                    depends = (previous_write,)
                previous_write = task.task_id
            elif previous_write:
                depends = (previous_write,)
                group = index
            else:
                group = 0
            planned.append(
                task.model_copy(update={"depends_on": depends, "parallel_group": group})
            )
        return tuple(planned)
