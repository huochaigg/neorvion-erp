from datetime import datetime

from sqlalchemy import Select, func, or_, select

from app.models.async_task import AsyncTask, AsyncTaskLog
from app.repositories.base import BaseRepository


class AsyncTaskRepository(BaseRepository):
    def add(self, row: AsyncTask) -> AsyncTask:
        self.session.add(row)
        return row

    def add_log(self, row: AsyncTaskLog) -> AsyncTaskLog:
        self.session.add(row)
        return row

    def get_by_task_id(self, task_id: str) -> AsyncTask | None:
        tenant_id = self.ensure_tenant()
        stmt = select(AsyncTask).where(
            AsyncTask.task_id == task_id,
            AsyncTask.tenant_id == tenant_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def lock_by_task_id(self, task_id: str) -> AsyncTask | None:
        """锁住当前租户的任务行，供重试和取消，避免并发重复入队。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(AsyncTask)
            .where(AsyncTask.task_id == task_id, AsyncTask.tenant_id == tenant_id)
            .with_for_update()
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_logs(self, task_id: str) -> list[AsyncTaskLog]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(AsyncTaskLog)
            .where(AsyncTaskLog.task_id == task_id, AsyncTaskLog.tenant_id == tenant_id)
            .order_by(AsyncTaskLog.id.asc())
        )
        return list(self.session.execute(stmt).scalars())

    def _filtered(
        self,
        *,
        task_type: str | None,
        status: str | None,
        created_by: int | None,
        created_from: datetime | None,
        created_to: datetime | None,
        keyword: str | None,
    ) -> Select[AsyncTask]:
        tenant_id = self.ensure_tenant()
        stmt = select(AsyncTask).where(AsyncTask.tenant_id == tenant_id)
        if task_type:
            stmt = stmt.where(AsyncTask.task_type == task_type)
        if status:
            stmt = stmt.where(AsyncTask.status == status)
        if created_by is not None:
            stmt = stmt.where(AsyncTask.created_by == created_by)
        if created_from is not None:
            stmt = stmt.where(AsyncTask.created_at >= created_from)
        if created_to is not None:
            stmt = stmt.where(AsyncTask.created_at < created_to)
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(or_(AsyncTask.title.like(like), AsyncTask.task_id.like(like)))
        return stmt

    def list_tasks(
        self,
        *,
        task_type: str | None = None,
        status: str | None = None,
        created_by: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AsyncTask], int]:
        filtered = self._filtered(
            task_type=task_type,
            status=status,
            created_by=created_by,
            created_from=created_from,
            created_to=created_to,
            keyword=keyword,
        )
        total = int(
            self.session.execute(select(func.count()).select_from(filtered.subquery())).scalar_one()
        )
        rows = list(
            self.session.scalars(
                filtered.order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, total
