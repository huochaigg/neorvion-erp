from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DbSession
from app.api.rbac_deps import (
    TaskCancelContext,
    TaskDownloadContext,
    TaskReadContext,
    TaskRetryContext,
)
from app.schemas.async_task import AsyncTaskListOut, AsyncTaskLogOut, AsyncTaskOut
from app.schemas.common import ApiResponse, ok
from app.services.async_task import AsyncTaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=ApiResponse[AsyncTaskListOut], summary="任务列表")
def list_tasks(
    context: TaskReadContext,
    session: DbSession,
    task_type: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    created_by: int | None = Query(default=None, gt=0),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    keyword: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[AsyncTaskListOut]:
    return ok(
        AsyncTaskService(session, context).list_tasks(
            task_type=task_type,
            status=status,
            created_by=created_by,
            created_from=created_from,
            created_to=created_to,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{task_id}", response_model=ApiResponse[AsyncTaskOut], summary="任务详情")
def get_task(
    task_id: str,
    context: TaskReadContext,
    session: DbSession,
) -> ApiResponse[AsyncTaskOut]:
    return ok(AsyncTaskService(session, context).get_task(task_id))


@router.get(
    "/{task_id}/logs",
    response_model=ApiResponse[list[AsyncTaskLogOut]],
    summary="任务日志",
)
def get_task_logs(
    task_id: str,
    context: TaskReadContext,
    session: DbSession,
) -> ApiResponse[list[AsyncTaskLogOut]]:
    return ok(AsyncTaskService(session, context).list_logs(task_id))


@router.post("/{task_id}/retry", response_model=ApiResponse[AsyncTaskOut], summary="重试或重新入队")
def retry_task(
    task_id: str,
    context: TaskRetryContext,
    session: DbSession,
) -> ApiResponse[AsyncTaskOut]:
    return ok(AsyncTaskService(session, context).retry(task_id), "已重新入队")


@router.post(
    "/{task_id}/cancel",
    response_model=ApiResponse[AsyncTaskOut],
    summary="取消等待中任务",
)
def cancel_task(
    task_id: str,
    context: TaskCancelContext,
    session: DbSession,
) -> ApiResponse[AsyncTaskOut]:
    return ok(AsyncTaskService(session, context).cancel(task_id), "已取消")


@router.get("/{task_id}/download", summary="下载任务结果")
def download_task(
    task_id: str,
    context: TaskDownloadContext,
    session: DbSession,
) -> FileResponse:
    path, filename = AsyncTaskService(session, context).download_path(task_id)
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "export.csv"
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
        )
    }
    return FileResponse(path, media_type="text/csv; charset=utf-8", headers=headers)
