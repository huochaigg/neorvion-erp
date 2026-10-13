from fastapi import APIRouter, Query

from app.api.deps import DbSession, KnowledgeReadContext
from app.schemas.common import ApiResponse, ok
from app.schemas.evaluation import UsageStatsOut
from app.services.usage_stats import UsageStatsService

router = APIRouter(tags=["knowledge-stats"])


@router.get("/stats/usage", response_model=ApiResponse[UsageStatsOut], summary="检索与问答使用统计")
async def usage_stats(
    context: KnowledgeReadContext,
    session: DbSession,
    days: int = Query(default=7, ge=1, le=90),
) -> ApiResponse[UsageStatsOut]:
    return ok(await UsageStatsService(session, context).overview(days))
