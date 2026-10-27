from fastapi import APIRouter, Query, Request

from app.api.deps import DbSession, GovernanceManageContext, GovernanceReadContext
from app.schemas.common import ApiResponse, ok
from app.schemas.governance import (
    GovernanceAuditOut,
    GovernancePolicyIn,
    GovernancePolicyOut,
    ModelCreate,
    ModelOut,
    ProviderCreate,
    ProviderOut,
    ProviderPatch,
    RetentionPreviewIn,
    TenantQuotaIn,
    TenantQuotaOut,
)
from app.services.governance import GovernanceService

router = APIRouter(prefix="/governance", tags=["ai-governance"])


def _service(request: Request, db: DbSession, context: GovernanceReadContext) -> GovernanceService:
    return GovernanceService(db, context, str(getattr(request.state, "request_id", "")))


@router.get("/providers", response_model=ApiResponse[list[ProviderOut]])
async def providers(request: Request, context: GovernanceReadContext, db: DbSession):
    return ok(await _service(request, db, context).providers())


@router.post("/providers", response_model=ApiResponse[ProviderOut])
async def create_provider(
    payload: ProviderCreate, request: Request, context: GovernanceManageContext, db: DbSession
):
    return ok(await _service(request, db, context).create_provider(payload))


@router.patch("/providers/{provider_id}", response_model=ApiResponse[ProviderOut])
async def patch_provider(
    provider_id: int,
    payload: ProviderPatch,
    request: Request,
    context: GovernanceManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).patch_provider(provider_id, payload))


@router.post("/providers/{provider_id}/probe", response_model=ApiResponse[ProviderOut])
async def probe_provider(
    provider_id: int, request: Request, context: GovernanceManageContext, db: DbSession
):
    return ok(await _service(request, db, context).probe_provider(provider_id))


@router.get("/models", response_model=ApiResponse[list[ModelOut]])
async def models(request: Request, context: GovernanceReadContext, db: DbSession):
    return ok(await _service(request, db, context).models())


@router.post("/models", response_model=ApiResponse[ModelOut])
async def create_model(
    payload: ModelCreate, request: Request, context: GovernanceManageContext, db: DbSession
):
    return ok(await _service(request, db, context).create_model(payload))


@router.get("/policy", response_model=ApiResponse[GovernancePolicyOut])
async def policy(request: Request, context: GovernanceReadContext, db: DbSession):
    return ok(await _service(request, db, context).policy())


@router.put("/policy", response_model=ApiResponse[GovernancePolicyOut])
async def replace_policy(
    payload: GovernancePolicyIn,
    request: Request,
    context: GovernanceManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).replace_policy(payload))


@router.get("/quota", response_model=ApiResponse[TenantQuotaOut])
async def quota(request: Request, context: GovernanceReadContext, db: DbSession):
    return ok(await _service(request, db, context).quota())


@router.put("/quota", response_model=ApiResponse[TenantQuotaOut])
async def replace_quota(
    payload: TenantQuotaIn,
    request: Request,
    context: GovernanceManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).replace_quota(payload))


@router.get("/usage", response_model=ApiResponse[dict])
async def usage(request: Request, context: GovernanceReadContext, db: DbSession):
    return ok(await _service(request, db, context).usage())


@router.get("/operations", response_model=ApiResponse[dict])
async def operations(request: Request, context: GovernanceReadContext, db: DbSession):
    return ok(await _service(request, db, context).operations())


@router.get("/audits", response_model=ApiResponse[list[GovernanceAuditOut]])
async def audits(
    request: Request,
    context: GovernanceReadContext,
    db: DbSession,
    limit: int = Query(100, ge=1, le=500),
):
    return ok(await _service(request, db, context).audits(limit))


@router.post("/retention/preview", response_model=ApiResponse[dict])
async def retention_preview(
    payload: RetentionPreviewIn,
    request: Request,
    context: GovernanceManageContext,
    db: DbSession,
):
    row = await _service(request, db, context).retention_preview(payload.dry_run)
    return ok(
        {
            "run_id": row.id,
            "dry_run": row.dry_run,
            "status": row.status,
            "cutoff_summary": row.cutoff_summary,
            "affected_summary": row.affected_summary,
        }
    )
