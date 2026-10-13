from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import OperationLogReadContext
from app.schemas.common import ApiResponse, ok
from app.schemas.operation_log import OperationLogListOut, OperationLogOut
from app.services.operation_query import OperationQueryService

router = APIRouter(prefix="/operation-logs", tags=["operation-logs"])


@router.get("", response_model=ApiResponse[OperationLogListOut], summary="操作日志列表")
def list_operation_logs(
    context: OperationLogReadContext,
    session: DbSession,
    operator_user_id: int | None = Query(default=None, gt=0),
    module: str | None = Query(default=None, max_length=32),
    action: str | None = Query(default=None, max_length=32),
    resource_type: str | None = Query(default=None, max_length=32),
    resource_id: int | None = Query(default=None, gt=0),
    result: str | None = Query(default=None, max_length=16),
    occurred_from: Annotated[datetime | None, Query()] = None,
    occurred_to: Annotated[datetime | None, Query()] = None,
    keyword: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[OperationLogListOut]:
    return ok(
        OperationQueryService(session, context).list_logs(
            operator_user_id=operator_user_id,
            module=module,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{log_id}", response_model=ApiResponse[OperationLogOut], summary="操作日志详情")
def get_operation_log(
    log_id: int,
    context: OperationLogReadContext,
    session: DbSession,
) -> ApiResponse[OperationLogOut]:
    return ok(OperationQueryService(session, context).get_log(log_id))
