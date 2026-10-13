from datetime import datetime

from sqlalchemy import Select, func, or_, select

from app.models.operation_log import OperationLog
from app.repositories.base import BaseRepository


class OperationLogRepository(BaseRepository):
    def add(self, row: OperationLog) -> OperationLog:
        self.session.add(row)
        return row

    def get_by_id(self, log_id: int) -> OperationLog | None:
        stmt = select(OperationLog).where(OperationLog.id == log_id)
        if self.tenant_id is not None:
            stmt = stmt.where(OperationLog.tenant_id == self.tenant_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def _filtered(
        self,
        *,
        operator_user_id: int | None,
        module: str | None,
        action: str | None,
        resource_type: str | None,
        resource_id: int | None,
        result: str | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        keyword: str | None,
    ) -> Select[tuple[OperationLog]]:
        stmt = select(OperationLog)
        if self.tenant_id is not None:
            stmt = stmt.where(OperationLog.tenant_id == self.tenant_id)
        else:
            stmt = stmt.where(OperationLog.tenant_id.is_(None))
        if operator_user_id is not None:
            stmt = stmt.where(OperationLog.operator_user_id == operator_user_id)
        if module:
            stmt = stmt.where(OperationLog.module == module)
        if action:
            stmt = stmt.where(OperationLog.action == action)
        if resource_type:
            stmt = stmt.where(OperationLog.resource_type == resource_type)
        if resource_id is not None:
            stmt = stmt.where(OperationLog.resource_id == resource_id)
        if result:
            stmt = stmt.where(OperationLog.result == result)
        if occurred_from is not None:
            stmt = stmt.where(OperationLog.occurred_at >= occurred_from)
        if occurred_to is not None:
            stmt = stmt.where(OperationLog.occurred_at < occurred_to)
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    OperationLog.description.like(like),
                    OperationLog.resource_name.like(like),
                    OperationLog.request_id.like(like),
                )
            )
        return stmt

    def list_logs(
        self,
        *,
        operator_user_id: int | None = None,
        module: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        result: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[OperationLog], int]:
        filtered = self._filtered(
            operator_user_id=operator_user_id,
            module=module,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            keyword=keyword,
        )
        total = int(
            self.session.execute(select(func.count()).select_from(filtered.subquery())).scalar_one()
        )
        rows = list(
            self.session.execute(
                filtered.order_by(OperationLog.occurred_at.desc(), OperationLog.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
        )
        return rows, total
