from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_api_scope
from app.core.tenant import TenantContext
from app.schemas.common import ApiResponse, ok
from app.schemas.evaluation import UsageStatsOut
from app.services.usage_stats import UsageStatsService

router = APIRouter(tags=["knowledge-stats"])


@router.get("/stats/usage", response_model=ApiResponse[UsageStatsOut], summary="检索与问答使用统计")
async def usage_stats(
    context: Annotated[TenantContext, Depends(require_api_scope("stats"))],
    session: DbSession,
    days: int = Query(default=7, ge=1, le=90),
) -> ApiResponse[UsageStatsOut]:
    return ok(await UsageStatsService(session, context).overview(days))
