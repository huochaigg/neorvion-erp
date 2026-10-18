from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.common import ApiResponse, ok
from app.schemas.health import HealthCheckData
from app.services.health import HealthService

router = APIRouter()


@router.get(
    "/health",
    response_model=ApiResponse[HealthCheckData],
    summary="健康检查",
)
async def health_check(session: DbSession) -> ApiResponse[HealthCheckData]:
    """探活 FastAPI、PostgreSQL、pgvector 与 IAM JWKS / 快照 Redis。

    依赖不可用时仍返回 HTTP 200，由字段标记 unavailable / not_installed。
    """
    data = await HealthService(session).check()
    return ok(data)
