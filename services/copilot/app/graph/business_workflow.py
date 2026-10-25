from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, TypedDict, cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.config import settings
from app.core.exceptions import AppError


class BusinessWorkflowState(TypedDict, total=False):
    workflow_id: int
    tenant_id: int
    user_id: int
    workflow_type: str
    phase: str
    resume: dict[str, Any]


def _validate(state: BusinessWorkflowState) -> dict[str, str]:
    return {"phase": "validated"}


def _wait_input(state: BusinessWorkflowState) -> dict[str, Any]:
    decision = interrupt({"kind": "workflow_input", "workflow_id": state.get("workflow_id")})
    return {"phase": "resumed", "resume": decision}


def _after_validate(state: BusinessWorkflowState) -> str:
    return "finalize" if state.get("workflow_type") == "SALES_ORDER_REVIEW_WORKFLOW" else "wait_input"


def _finalize(state: BusinessWorkflowState) -> dict[str, str]:
    _ = state
    return {"phase": "finalized"}


class BusinessWorkflowGraph:
    """V7 独立编排图；业务状态、权限和执行结果仍由 Workflow/V6 Service 权威保存。"""

    def __init__(self) -> None:
        self._manager: AbstractAsyncContextManager | None = None
        self._graph = None

    async def start(self) -> None:
        if self._graph is not None:
            return
        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._manager = AsyncPostgresSaver.from_conn_string(dsn)
        saver = await self._manager.__aenter__()
        await saver.setup()
        builder = StateGraph(BusinessWorkflowState)
        builder.add_node("validate", _validate)
        builder.add_node("wait_input", _wait_input)
        builder.add_node("finalize", _finalize)
        builder.add_edge(START, "validate")
        builder.add_conditional_edges("validate", _after_validate)
        builder.add_edge("wait_input", "finalize")
        builder.add_edge("finalize", END)
        self._graph = builder.compile(checkpointer=saver)

    async def close(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
        self._manager = None
        self._graph = None

    @staticmethod
    def config(workflow_id: int) -> dict[str, Any]:
        return {"configurable": {"thread_id": f"business-workflow:{workflow_id}"}}

    async def begin(self, state: BusinessWorkflowState) -> None:
        if self._graph is None:
            raise AppError("工作流编排尚未就绪", code=50377, status_code=503)
        await self._graph.ainvoke(state, cast(Any, self.config(state.get("workflow_id") or 0)))

    async def resume(self, workflow_id: int, decision: dict[str, Any]) -> None:
        if self._graph is None:
            raise AppError("工作流编排尚未就绪", code=50377, status_code=503)
        await self._graph.ainvoke(Command(resume=decision), cast(Any, self.config(workflow_id)))


business_workflow_graph = BusinessWorkflowGraph()
