from typing import cast

from fastapi import APIRouter, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CopilotContext, DbSession
from app.erp.client import get_erp_client
from app.schemas.action_proposal import (
    ActionProposalCancel,
    ActionProposalCreate,
    ActionProposalListOut,
    ActionProposalOut,
    ActionProposalUpdate,
    ActionProposalValidate,
    ProposalRevisionListOut,
)
from app.schemas.common import ApiResponse, ok
from app.services.action_proposals import ActionProposalService

router = APIRouter(prefix="/action-proposals", tags=["action-proposals"])


def _service(request: Request, db: DbSession, context: CopilotContext) -> ActionProposalService:
    return ActionProposalService(
        cast(AsyncSession, db),
        context,
        erp_client=get_erp_client(),
        access_token=str(getattr(request.state, "access_token", "")),
        request_id=str(getattr(request.state, "request_id", "")),
    )


@router.post("", response_model=ApiResponse[ActionProposalOut])
async def create_action_proposal(
    payload: ActionProposalCreate, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).create(payload), "业务草稿已生成")


@router.get("", response_model=ApiResponse[ActionProposalListOut])
async def list_action_proposals(
    request: Request,
    context: CopilotContext,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    conversation_id: int | None = Query(default=None, gt=0),
):
    return ok(await _service(request, db, context).list(page, page_size, conversation_id))


@router.get("/{proposal_id}", response_model=ApiResponse[ActionProposalOut])
async def get_action_proposal(
    proposal_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).get(proposal_id))


@router.patch("/{proposal_id}", response_model=ApiResponse[ActionProposalOut])
async def update_action_proposal(
    proposal_id: int,
    payload: ActionProposalUpdate,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).update(proposal_id, payload), "草稿已保存")


@router.post("/{proposal_id}/validate", response_model=ApiResponse[ActionProposalOut])
async def validate_action_proposal(
    proposal_id: int,
    payload: ActionProposalValidate,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).validate(proposal_id, payload.expected_revision))


@router.post("/{proposal_id}/cancel", response_model=ApiResponse[ActionProposalOut])
async def cancel_action_proposal(
    proposal_id: int,
    payload: ActionProposalCancel,
    request: Request,
    context: CopilotContext,
    db: DbSession,
):
    return ok(
        await _service(request, db, context).cancel(proposal_id, payload.expected_revision),
        "草稿已取消",
    )


@router.get("/{proposal_id}/revisions", response_model=ApiResponse[ProposalRevisionListOut])
async def list_action_proposal_revisions(
    proposal_id: int, request: Request, context: CopilotContext, db: DbSession
):
    return ok(await _service(request, db, context).revisions(proposal_id))
