from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ApiResponse, ok
from app.schemas.health import HealthCheckData
from app.services.health import HealthService

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/health",
    response_model=ApiResponse[HealthCheckData],
    summary="健康检查",
)
def health_check(session: DbSession) -> ApiResponse[HealthCheckData]:
    """探活 FastAPI、MySQL 和 Redis。

    输入：无。
    输出：`data.app/mysql/redis` 状态以及当前里程碑。
    规则：依赖不可用时仍返回 HTTP 200，由字段标记 unavailable，便于前端展示。
    """
    data = HealthService(session).check()
    return ok(data)
