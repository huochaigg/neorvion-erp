from fastapi import APIRouter

from app.core.config import settings
from app.core.iam import ping_iam_store
from app.schemas.common import ApiResponse, ok
from app.schemas.health import HealthCheckData

router = APIRouter()


@router.get("/health", response_model=ApiResponse[HealthCheckData], summary="健康检查")
async def health_check() -> ApiResponse[HealthCheckData]:
    return ok(
        HealthCheckData(
            version=settings.app_version,
            git_sha=settings.git_sha,
            identity="ok" if ping_iam_store() else "unavailable",
        )
    )

