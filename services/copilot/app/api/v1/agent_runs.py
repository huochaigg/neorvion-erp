from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CopilotContext, DbSession
from app.core.exceptions import AppError
from app.models.agent_trace import AgentRun, AgentTaskRun
from app.models.conversation import Evidence, ToolRun
from app.models.evaluation import ModelCall
from app.schemas.common import ApiResponse, ok

router = APIRouter(prefix="/agent-runs", tags=["agent-trace"])


@router.get("/{run_id}/trace", response_model=ApiResponse[dict])
async def agent_trace(run_id: int, context: CopilotContext, db: DbSession):
    """返回运行树所需的脱敏步骤，不包含 Prompt、JWT 或模型隐藏思维。"""
    run = await db.scalar(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.tenant_id == context.tenant_id,
            AgentRun.user_id == context.user_id,
        )
    )
    if run is None:
        raise AppError("Agent Run 不存在", code=40494, status_code=404)
    tasks = list(
        (
            await db.scalars(
                select(AgentTaskRun)
                .where(
                    AgentTaskRun.tenant_id == context.tenant_id, AgentTaskRun.agent_run_id == run.id
                )
                .order_by(AgentTaskRun.started_at)
            )
        ).all()
    )
    calls = list(
        (
            await db.scalars(
                select(ModelCall)
                .where(
                    ModelCall.tenant_id == context.tenant_id,
                    ModelCall.user_id == context.user_id,
                    ModelCall.agent_run_id == run.id,
                )
                .order_by(ModelCall.started_at)
            )
        ).all()
    )
    tools = list(
        (
            await db.scalars(
                select(ToolRun)
                .where(ToolRun.tenant_id == context.tenant_id, ToolRun.message_id == run.message_id)
                .order_by(ToolRun.created_at)
            )
        ).all()
    )
    evidences = list(
        (
            await db.scalars(
                select(Evidence)
                .where(
                    Evidence.tenant_id == context.tenant_id,
                    Evidence.user_id == context.user_id,
                    Evidence.message_id == run.message_id,
                )
                .order_by(Evidence.created_at)
            )
        ).all()
    )

    def safe(row, fields: tuple[str, ...]) -> dict:
        return {field: getattr(row, field) for field in fields}

    return ok(
        {
            "agent_run": safe(
                run,
                (
                    "id",
                    "request_id",
                    "graph_type",
                    "status",
                    "started_at",
                    "completed_at",
                    "total_duration_ms",
                    "error_code",
                ),
            ),
            "tasks": [
                safe(
                    x,
                    (
                        "id",
                        "agent_name",
                        "task_id",
                        "status",
                        "duration_ms",
                        "model_calls",
                        "tool_calls",
                        "evidence_count",
                        "error_code",
                    ),
                )
                for x in tasks
            ],
            "model_calls": [
                safe(
                    x,
                    (
                        "id",
                        "agent_task_id",
                        "model_call_id",
                        "model_provider",
                        "model_name",
                        "status",
                        "duration_ms",
                        "input_tokens",
                        "output_tokens",
                        "usage_source",
                        "estimated_cost",
                        "currency",
                        "error_code",
                    ),
                )
                for x in calls
            ],
            "tool_runs": [
                safe(
                    x,
                    (
                        "id",
                        "agent_task_id",
                        "tool_call_id",
                        "tool_name",
                        "status",
                        "duration_ms",
                        "error_code",
                    ),
                )
                for x in tools
            ],
            "evidences": [
                safe(
                    x,
                    (
                        "id",
                        "agent_task_id",
                        "source_agent",
                        "citation_id",
                        "source_type",
                        "resource_type",
                        "resource_id",
                        "observed_at",
                    ),
                )
                for x in evidences
            ],
        }
    )
