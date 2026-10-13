from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.operation_log import OperationLog
from app.repositories.operation_log import OperationLogRepository
from app.schemas.operation_log import OperationLogListOut, OperationLogOut


def log_out(row: OperationLog) -> OperationLogOut:
    return OperationLogOut(
        id=row.id,
        tenant_id=row.tenant_id,
        operator_user_id=row.operator_user_id,
        action=row.action,
        module=row.module,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        resource_name=row.resource_name,
        request_method=row.request_method,
        request_path=row.request_path,
        request_id=row.request_id,
        result=row.result,
        error_code=row.error_code,
        description=row.description,
        metadata=row.extra_metadata,
        occurred_at=row.occurred_at,
    )


class OperationQueryService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.repo = OperationLogRepository(session, context.tenant_id)

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
    ) -> OperationLogListOut:
        rows, total = self.repo.list_logs(
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
        return OperationLogListOut(
            items=[log_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_log(self, log_id: int) -> OperationLogOut:
        row = self.repo.get_by_id(log_id)
        if row is None:
            raise AppError("操作日志不存在或不可访问", code=40701, status_code=404)
        return log_out(row)
