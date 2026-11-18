from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile

from app.api.deps import (
    DbSession,
    McpManageContext,
    McpReadContext,
    SkillManageContext,
    SkillReadContext,
    SkillRunContext,
    WorkflowDep,
)
from app.core.exceptions import AppError
from app.schemas.common import ApiResponse, ok
from app.schemas.ecosystem import (
    McpApprovalIn,
    McpServerCreate,
    McpServerOut,
    McpServerPatch,
    McpToolOut,
    McpToolReviewIn,
    SkillCreate,
    SkillDetailOut,
    SkillOut,
    SkillRollbackIn,
    SkillRunIn,
    SkillRunOut,
    SkillTemplateImportIn,
    SkillTemplateImportOut,
    SkillVersionIn,
)
from app.services.ecosystem import EcosystemService
from app.services.skill_execution import SkillExecutionService

router = APIRouter(prefix="/ecosystem", tags=["copilot-ecosystem"])


def _service(request: Request, db: DbSession, context) -> EcosystemService:
    return EcosystemService(
        db,
        context,
        str(getattr(request.state, "request_id", "")),
    )


@router.get("/mcp/servers", response_model=ApiResponse[list[McpServerOut]])
async def list_servers(request: Request, context: McpReadContext, db: DbSession):
    return ok(await _service(request, db, context).servers())


@router.post("/mcp/servers", response_model=ApiResponse[McpServerOut])
async def create_server(
    payload: McpServerCreate,
    request: Request,
    context: McpManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).create_server(payload))


@router.patch("/mcp/servers/{server_id}", response_model=ApiResponse[McpServerOut])
async def patch_server(
    server_id: int,
    payload: McpServerPatch,
    request: Request,
    context: McpManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).patch_server(server_id, payload))


@router.post("/mcp/servers/{server_id}/review", response_model=ApiResponse[McpServerOut])
async def review_server(
    server_id: int,
    payload: McpApprovalIn,
    request: Request,
    context: McpManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).review_server(server_id, payload.approved))


@router.post("/mcp/servers/{server_id}/enabled", response_model=ApiResponse[McpServerOut])
async def enable_server(
    server_id: int,
    payload: McpApprovalIn,
    request: Request,
    context: McpManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).set_server_enabled(server_id, payload.approved))


@router.post("/mcp/servers/{server_id}/probe", response_model=ApiResponse[McpServerOut])
async def probe_server(server_id: int, request: Request, context: McpManageContext, db: DbSession):
    return ok(await _service(request, db, context).probe(server_id))


@router.post("/mcp/servers/{server_id}/discover", response_model=ApiResponse[list[McpToolOut]])
async def discover_tools(
    server_id: int, request: Request, context: McpManageContext, db: DbSession
):
    return ok(await _service(request, db, context).discover(server_id))


@router.get("/mcp/tools", response_model=ApiResponse[list[McpToolOut]])
async def list_tools(request: Request, context: McpReadContext, db: DbSession):
    return ok(await _service(request, db, context).tools())


@router.post("/mcp/tools/{tool_id}/review", response_model=ApiResponse[McpToolOut])
async def review_tool(
    tool_id: int,
    payload: McpToolReviewIn,
    request: Request,
    context: McpManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).review_tool(tool_id, payload))


@router.get("/skills", response_model=ApiResponse[list[SkillOut]])
async def list_skills(request: Request, context: SkillReadContext, db: DbSession):
    return ok(await _service(request, db, context).skills())


@router.post("/skills", response_model=ApiResponse[SkillDetailOut])
async def create_skill(
    payload: SkillCreate,
    request: Request,
    context: SkillManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).create_skill(payload))


@router.post("/skills/templates/import", response_model=ApiResponse[list[SkillTemplateImportOut]])
async def import_skill_templates(
    payload: SkillTemplateImportIn,
    request: Request,
    context: SkillManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).import_skill_templates(payload.skill_keys))


@router.post("/skills/packages/import", response_model=ApiResponse[SkillTemplateImportOut])
async def import_skill_package(
    request: Request,
    context: SkillManageContext,
    db: DbSession,
    archive: Annotated[UploadFile, File(description="Agent Skill ZIP 包")],
):
    if not archive.filename or not archive.filename.lower().endswith(".zip"):
        raise AppError("只接受 ZIP Skill 包", code=42292, status_code=422)
    content = await archive.read(262_145)
    return ok(await _service(request, db, context).import_skill_package(content))


@router.get("/skills/{skill_id}", response_model=ApiResponse[SkillDetailOut])
async def get_skill(skill_id: int, request: Request, context: SkillReadContext, db: DbSession):
    return ok(await _service(request, db, context).skill(skill_id))


@router.get("/skills/{skill_id}/runs", response_model=ApiResponse[list[SkillRunOut]])
async def list_skill_runs(
    skill_id: int, request: Request, context: SkillReadContext, db: DbSession
):
    return ok(await _service(request, db, context).skill_runs(skill_id))


@router.get("/skills/{skill_id}/runs/{run_id}", response_model=ApiResponse[SkillRunOut])
async def get_skill_run(
    skill_id: int, run_id: int, request: Request, context: SkillReadContext, db: DbSession
):
    return ok(await _service(request, db, context).skill_run(skill_id, run_id))


@router.post("/skills/{skill_id}/versions", response_model=ApiResponse[SkillDetailOut])
async def create_skill_version(
    skill_id: int,
    payload: SkillVersionIn,
    request: Request,
    context: SkillManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).add_skill_version(skill_id, payload))


@router.post("/skills/{skill_id}/review", response_model=ApiResponse[SkillDetailOut])
async def review_skill(
    skill_id: int,
    payload: McpApprovalIn,
    request: Request,
    context: SkillManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).review_skill(skill_id, payload.approved))


@router.post("/skills/{skill_id}/enabled", response_model=ApiResponse[SkillDetailOut])
async def enable_skill(
    skill_id: int,
    payload: McpApprovalIn,
    request: Request,
    context: SkillManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).set_skill_enabled(skill_id, payload.approved))


@router.post("/skills/{skill_id}/rollback", response_model=ApiResponse[SkillDetailOut])
async def rollback_skill(
    skill_id: int,
    payload: SkillRollbackIn,
    request: Request,
    context: SkillManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).rollback_skill(skill_id, payload.version))


@router.post("/skills/{skill_id}/runs", response_model=ApiResponse[SkillRunOut])
async def run_skill(
    skill_id: int,
    payload: SkillRunIn,
    request: Request,
    context: SkillRunContext,
    db: DbSession,
    workflow: WorkflowDep,
):
    service = SkillExecutionService(
        db,
        context,
        workflow,
        access_token=str(getattr(request.state, "access_token", "")),
        audiences=frozenset(getattr(request.state, "jwt_audiences", ())),
        request_id=str(getattr(request.state, "request_id", "")),
    )
    return ok(await service.run(skill_id, payload))
