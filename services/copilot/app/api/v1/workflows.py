from typing import cast

from fastapi import APIRouter, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CopilotContext, DbSession
from app.erp.client import get_erp_client
from app.knowledge.client import get_knowledge_client
from app.schemas.common import ApiResponse, ok
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowDetailOut,
    WorkflowEventOut,
    WorkflowListOut,
    WorkflowMetricsOut,
    WorkflowOut,
    WorkflowResume,
    WorkflowStepOut,
)
from app.services.workflows import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _service(request: Request, db: DbSession, context: CopilotContext) -> WorkflowService:
    return WorkflowService(
        cast(AsyncSession, db),
        context,
        access_token=str(getattr(request.state, "access_token", "")),
        request_id=str(getattr(request.state, "request_id", "")),
        erp=get_erp_client(),
        knowledge=get_knowledge_client(),
        audiences=tuple(getattr(request.state, "jwt_audiences", ())),
    )


@router.post("", response_model=ApiResponse[WorkflowOut])
async def create_workflow(
    payload: WorkflowCreate, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).create(payload))


@router.get("", response_model=ApiResponse[WorkflowListOut])
async def list_workflows(
    request: Request,
    context: CopilotContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(await _service(request, db, context).list(page, page_size))


@router.get("/metrics", response_model=ApiResponse[WorkflowMetricsOut])
async def workflow_metrics(request: Request, context: CopilotContext, db: DbSession):
    return ok(await _service(request, db, context).metrics())


@router.get("/{workflow_id}", response_model=ApiResponse[WorkflowDetailOut])
async def get_workflow(workflow_id: int, request: Request, context: CopilotContext, db: DbSession):
    return ok(await _service(request, db, context).detail(workflow_id))


@router.get("/{workflow_id}/steps", response_model=ApiResponse[list[WorkflowStepOut]])
async def workflow_steps(
    workflow_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok((await _service(request, db, context).detail(workflow_id)).steps)


@router.get("/{workflow_id}/events", response_model=ApiResponse[list[WorkflowEventOut]])
async def workflow_events(
    workflow_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok((await _service(request, db, context).detail(workflow_id)).events)


@router.post("/{workflow_id}/resume", response_model=ApiResponse[WorkflowOut])
async def resume_workflow(
    workflow_id: int,
    payload: WorkflowResume,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    service = _service(request, db, context)
    values = dict(payload.input)
    execution_id = values.pop("execution_id", None)
    if execution_id is not None:
        return ok(await service.attach_execution(workflow_id, int(execution_id)))
    return ok(await service.advance(workflow_id, values))


@router.post("/{workflow_id}/retry", response_model=ApiResponse[WorkflowOut])
async def retry_workflow(
    workflow_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).advance(workflow_id, {}))


@router.post("/{workflow_id}/cancel", response_model=ApiResponse[WorkflowOut])
async def cancel_workflow(
    workflow_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).cancel(workflow_id))
