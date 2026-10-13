"""异步任务创建、重试、取消与下载。状态以 MySQL 为准。"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.async_tasks import (
    CANCELLABLE_STATUSES,
    REPORT_EXPORT_KINDS,
    RETRYABLE_STATUSES,
    TASK_ID_PREFIX,
    TASK_MAX_RETRIES,
    TaskStatus,
    TaskType,
)
from app.core.exceptions import AppError
from app.core.operations import OperationAction, OperationModule
from app.core.sanitize import sanitize_payload
from app.core.tenant import TenantContext
from app.models.async_task import AsyncTask
from app.repositories.async_task import AsyncTaskRepository
from app.schemas.async_task import (
    AsyncTaskListOut,
    AsyncTaskLogOut,
    AsyncTaskOut,
    ReportExportCreate,
)
from app.services.observability import emit_operation
from app.tasks.handlers import export_dir_for
from app.tasks.queue import enqueue_task

_KIND_TITLES = {
    "sales_trend": "导出销售按日汇总",
    "purchase_trend": "导出采购按日汇总",
    "low_stock": "导出低库存列表",
}


def new_task_id() -> str:
    return f"{TASK_ID_PREFIX}{uuid.uuid4().hex}"


def task_out(row: AsyncTask, *, queued: bool | None = None) -> AsyncTaskOut:
    return AsyncTaskOut(
        id=row.id,
        task_id=row.task_id,
        task_type=row.task_type,
        status=row.status,
        progress=row.progress,
        title=row.title,
        description=row.description,
        payload=row.payload,
        result=row.result,
        error_message=row.error_message,
        retry_count=row.retry_count,
        max_retries=row.max_retries,
        created_by=row.created_by,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        queued=queued,
    )


class AsyncTaskService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.repo = AsyncTaskRepository(session, context.tenant_id)

    def list_tasks(self, **filters) -> AsyncTaskListOut:
        rows, total = self.repo.list_tasks(**filters)
        return AsyncTaskListOut(
            items=[task_out(row) for row in rows],
            total=total,
            page=filters.get("page", 1),
            page_size=filters.get("page_size", 20),
        )

    def get_task(self, task_id: str) -> AsyncTaskOut:
        row = self._require(task_id)
        return task_out(row)

    def list_logs(self, task_id: str) -> list[AsyncTaskLogOut]:
        self._require(task_id)
        return [AsyncTaskLogOut.model_validate(item) for item in self.repo.list_logs(task_id)]

    def create_report_export(self, payload: ReportExportCreate) -> AsyncTaskOut:
        """
        功能：创建 REPORT_EXPORT 任务并尝试入 Redis 队列。
        事务边界：先 commit 任务行，再推队列。队列失败则保持 PENDING。
        """
        kind = payload.kind
        if kind not in REPORT_EXPORT_KINDS:
            raise AppError("不支持的导出类型", code=40720, status_code=400)
        body = sanitize_payload(
            {
                "kind": kind,
                "start_date": payload.start_date,
                "end_date": payload.end_date,
                "warehouse_id": payload.warehouse_id,
                "low_stock_threshold": payload.low_stock_threshold,
            }
        )
        task = AsyncTask(
            tenant_id=self.context.tenant_id,
            task_id=new_task_id(),
            task_type=TaskType.REPORT_EXPORT.value,
            status=TaskStatus.PENDING.value,
            progress=0,
            title=_KIND_TITLES[kind],
            payload=body,
            retry_count=0,
            max_retries=TASK_MAX_RETRIES,
            created_by=self.context.user_id,
        )
        self.repo.add(task)
        emit_operation(
            self.session,
            self.context,
            action=OperationAction.EXPORT.value,
            module=OperationModule.ANALYTICS.value,
            resource_type="ASYNC_TASK",
            resource_name=task.task_id,
            description=task.title,
        )
        self.session.commit()
        queued = self._enqueue(task.task_id)
        refreshed = self._require(task.task_id)
        return task_out(refreshed, queued=queued)

    def retry(self, task_id: str) -> AsyncTaskOut:
        """
        功能：FAILED / PENDING 任务重新入队。SUCCESS 不可重试。
        并发：锁任务行，两个管理员同时点 Retry 只有一次能改状态。
        """
        try:
            task = self.repo.lock_by_task_id(task_id)
            if task is None:
                raise AppError("任务不存在或不可访问", code=40710, status_code=404)
            if task.status == TaskStatus.SUCCESS.value:
                raise AppError("成功任务不能重试", code=40711, status_code=400)
            if task.status not in RETRYABLE_STATUSES:
                raise AppError("当前状态不能重试或重新入队", code=40711, status_code=400)
            if task.retry_count >= task.max_retries and task.status == TaskStatus.FAILED.value:
                raise AppError("已达到最大重试次数", code=40711, status_code=400)
            if task.status == TaskStatus.FAILED.value:
                task.retry_count += 1
            # 同一把行锁内先标 QUEUED，避免两个管理员同时 Retry 都看到 FAILED/PENDING。
            task.status = TaskStatus.QUEUED.value
            task.error_message = None
            task.finished_at = None
            emit_operation(
                self.session,
                self.context,
                action=OperationAction.RETRY.value,
                module=OperationModule.TASK.value,
                resource_type="ASYNC_TASK",
                resource_id=task.id,
                resource_name=task.task_id,
                description="重新入队异步任务",
            )
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        queued = enqueue_task(task_id)
        if not queued:
            stuck = self.repo.lock_by_task_id(task_id)
            if stuck is not None and stuck.status == TaskStatus.QUEUED.value:
                stuck.status = TaskStatus.PENDING.value
                self.session.commit()
            return task_out(self._require(task_id), queued=False)
        return task_out(self._require(task_id), queued=True)

    def cancel(self, task_id: str) -> AsyncTaskOut:
        try:
            task = self.repo.lock_by_task_id(task_id)
            if task is None:
                raise AppError("任务不存在或不可访问", code=40710, status_code=404)
            if task.status not in CANCELLABLE_STATUSES:
                raise AppError("只能取消等待中或排队中的任务", code=40712, status_code=400)
            task.status = TaskStatus.CANCELLED.value
            from datetime import datetime

            task.finished_at = datetime.now()
            self.session.commit()
        except AppError:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
        return task_out(self._require(task_id))

    def download_path(self, task_id: str) -> tuple[Path, str]:
        task = self._require(task_id)
        if task.status != TaskStatus.SUCCESS.value:
            raise AppError("只有成功任务可以下载", code=40713, status_code=400)
        if task.task_type != TaskType.REPORT_EXPORT.value:
            raise AppError("该任务类型不支持下载", code=40713, status_code=400)
        path = export_dir_for(task.tenant_id, task.task_id)
        if not path.is_file():
            raise AppError("导出文件不存在", code=40713, status_code=404)
        name = str((task.result or {}).get("file_name") or f"{task.task_id}.csv")
        return path, name

    def _enqueue(self, task_id: str) -> bool:
        if not enqueue_task(task_id):
            return False
        session_task = self.repo.lock_by_task_id(task_id)
        if session_task is None:
            return False
        if session_task.status == TaskStatus.PENDING.value:
            session_task.status = TaskStatus.QUEUED.value
            self.session.commit()
        else:
            self.session.rollback()
        return True

    def _require(self, task_id: str) -> AsyncTask:
        row = self.repo.get_by_task_id(task_id)
        if row is None:
            raise AppError("任务不存在或不可访问", code=40710, status_code=404)
        return row
