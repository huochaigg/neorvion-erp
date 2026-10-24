from typing import cast

from fastapi import APIRouter, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CopilotContext, DbSession
from app.erp.client import get_erp_client
from app.schemas.action_execution import (
    ActionApprovalListOut,
    ActionAuditListOut,
    ActionExecutionListOut,
    ActionExecutionOut,
    ApprovalDecision,
    ConfirmationCreate,
    ConfirmationTicketOut,
    ExecutionConfirm,
    ExecutionResume,
)
from app.schemas.common import ApiResponse, ok
from app.services.action_executions import ActionExecutionService

router = APIRouter(tags=["action-executions"])


def _service(request: Request, db: DbSession, context: CopilotContext) -> ActionExecutionService:
    return ActionExecutionService(
        cast(AsyncSession, db),
        context,
        erp_client=get_erp_client(),
        access_token=str(getattr(request.state, "access_token", "")),
        request_id=str(getattr(request.state, "request_id", "")),
    )


@router.post(
    "/action-proposals/{proposal_id}/confirmations",
    response_model=ApiResponse[ConfirmationTicketOut],
)
async def create_confirmation(
    proposal_id: int,
    payload: ConfirmationCreate,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    return ok(
        await _service(request, db, context).create_confirmation(proposal_id, payload),
        "请明确确认执行",
    )


@router.post(
    "/action-executions/{execution_id}/confirm", response_model=ApiResponse[ActionExecutionOut]
)
async def confirm_execution(
    execution_id: int,
    payload: ExecutionConfirm,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    return ok(
        await _service(request, db, context).confirm(
            execution_id, payload.expected_revision, payload.confirmation_nonce
        )
    )


@router.post(
    "/action-executions/{execution_id}/execute", response_model=ApiResponse[ActionExecutionOut]
)
async def execute_action(
    execution_id: int,
    payload: ExecutionResume,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).execute(execution_id, payload.expected_revision))


@router.post(
    "/action-executions/{execution_id}/reconcile", response_model=ApiResponse[ActionExecutionOut]
)
async def reconcile_action(
    execution_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).reconcile(execution_id))


@router.get("/action-executions/{execution_id}", response_model=ApiResponse[ActionExecutionOut])
async def get_execution(
    execution_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).get(execution_id))


@router.get("/action-executions", response_model=ApiResponse[ActionExecutionListOut])
async def list_executions(
    request: Request,
    context: CopilotContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(await _service(request, db, context).list(page, page_size))


@router.get("/action-approvals", response_model=ApiResponse[ActionApprovalListOut])
async def list_approvals(
    request: Request,
    context: CopilotContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(await _service(request, db, context).approvals(page, page_size))


@router.post(
    "/action-approvals/{approval_id}/approve", response_model=ApiResponse[ActionExecutionOut]
)
async def approve(
    approval_id: int,
    payload: ApprovalDecision,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    return ok(
        await _service(request, db, context).decide(
            approval_id, approve=True, reason=payload.decision_reason
        ),
        "审批通过，申请人需重新验证权限后执行",
    )


@router.post(
    "/action-approvals/{approval_id}/reject", response_model=ApiResponse[ActionExecutionOut]
)
async def reject(
    approval_id: int,
    payload: ApprovalDecision,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    return ok(
        await _service(request, db, context).decide(
            approval_id, approve=False, reason=payload.decision_reason
        ),
        "已拒绝",
    )


@router.post(
    "/action-approvals/{approval_id}/revoke", response_model=ApiResponse[ActionExecutionOut]
)
async def revoke_approval(
    approval_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).revoke(approval_id), "审批申请已撤销")


@router.get(
    "/action-executions/{execution_id}/audit", response_model=ApiResponse[ActionAuditListOut]
)
async def execution_audit(
    execution_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).audit(execution_id))
