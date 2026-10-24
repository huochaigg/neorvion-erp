from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, TypedDict

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.core.config import settings
from app.core.exceptions import AppError


class ActionExecutionState(TypedDict, total=False):
    execution_id: int
    tenant_id: int
    user_id: int
    proposal_revision: int
    requires_approval: bool
    confirmation: dict[str, Any]
    approval: dict[str, Any]
    phase: str


def _request_confirmation(state: ActionExecutionState) -> dict[str, Any]:
    decision = interrupt(
        {
            "kind": "confirmation",
            "execution_id": state["execution_id"],
            "proposal_revision": state["proposal_revision"],
        }
    )
    return {"confirmation": decision, "phase": "confirmation_received"}


def _after_confirmation(state: ActionExecutionState) -> str:
    decision = state.get("confirmation", {})
    if (
        not decision.get("confirmed")
        or decision.get("execution_id") != state["execution_id"]
        or decision.get("tenant_id") != state["tenant_id"]
        or decision.get("proposal_revision") != state["proposal_revision"]
    ):
        return "end"
    return "request_approval" if state.get("requires_approval") else "final_revalidation"


def _request_approval(state: ActionExecutionState) -> dict[str, Any]:
    decision = interrupt(
        {
            "kind": "approval",
            "execution_id": state["execution_id"],
            "proposal_revision": state["proposal_revision"],
        }
    )
    return {"approval": decision, "phase": "approval_received"}


def _after_approval(state: ActionExecutionState) -> str:
    decision = state.get("approval", {})
    valid = (
        decision.get("approved")
        and decision.get("execution_id") == state["execution_id"]
        and decision.get("tenant_id") == state["tenant_id"]
        and decision.get("proposal_revision") == state["proposal_revision"]
    )
    return "final_revalidation" if valid else "end"


def _phase(name: str):
    def node(_state: ActionExecutionState) -> dict[str, Any]:
        return {"phase": name}

    return node


class ActionExecutionGraph:
    """使用官方 PostgreSQL Saver 的独立 HITL 图；业务状态和授权仍以数据库服务为准。"""

    def __init__(self) -> None:
        self._manager: AbstractAsyncContextManager | None = None
        self._saver: AsyncPostgresSaver | None = None
        self._graph = None

    async def start(self) -> None:
        if self._graph is not None:
            return
        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._manager = AsyncPostgresSaver.from_conn_string(dsn)
        self._saver = await self._manager.__aenter__()
        await self._saver.setup()
        builder = StateGraph(ActionExecutionState)
        builder.add_node("request_confirmation", _request_confirmation)
        builder.add_node("request_approval", _request_approval)
        builder.add_node("final_revalidation", _phase("final_revalidation"))
        builder.add_node("execute_erp", _phase("execute_erp"))
        builder.add_node("end", _phase("end"))
        builder.add_edge(START, "request_confirmation")
        builder.add_conditional_edges("request_confirmation", _after_confirmation)
        builder.add_conditional_edges("request_approval", _after_approval)
        builder.add_edge("final_revalidation", "execute_erp")
        builder.add_edge("execute_erp", "end")
        builder.add_edge("end", END)
        self._graph = builder.compile(checkpointer=self._saver)

    async def close(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
        self._manager = None
        self._saver = None
        self._graph = None

    @staticmethod
    def _config(execution_id: int) -> dict[str, Any]:
        return {"configurable": {"thread_id": f"action-execution:{execution_id}"}}

    async def begin(self, state: ActionExecutionState) -> None:
        if self._graph is None:
            raise AppError("执行编排尚未就绪", code=50376, status_code=503)
        await self._graph.ainvoke(state, self._config(state["execution_id"]))

    async def resume(self, execution_id: int, decision: dict[str, Any]) -> None:
        if self._graph is None:
            raise AppError("执行编排尚未就绪", code=50376, status_code=503)
        await self._graph.ainvoke(Command(resume=decision), self._config(execution_id))


action_execution_graph = ActionExecutionGraph()
