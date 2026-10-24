from fastapi import APIRouter

from app.ai.status import model_runtime_status
from app.core.config import settings
from app.core.iam import ping_iam_store
from app.schemas.common import ApiResponse, ok
from app.schemas.health import HealthCheckData, ModelStatusData

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


@router.get("/model-status", response_model=ApiResponse[ModelStatusData], summary="模型运行状态")
async def model_status() -> ApiResponse[ModelStatusData]:
    return ok(ModelStatusData.model_validate(await model_runtime_status()))
