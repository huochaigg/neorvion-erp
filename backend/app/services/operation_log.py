"""操作日志写入。成功记录跟随业务事务；失败记录在 rollback 之后单独提交。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.operations import OperationResult
from app.core.request_id import get_request_id
from app.core.sanitize import sanitize_payload
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.operation_log import OperationLog
from app.repositories.operation_log import OperationLogRepository


class OperationLogService:
    def __init__(self, session: Session, tenant_id: int | None) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repo = OperationLogRepository(session, tenant_id)

    def write(
        self,
        *,
        action: str,
        module: str,
        result: str = OperationResult.SUCCESS.value,
        operator_user_id: int | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        resource_name: str | None = None,
        description: str | None = None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
    ) -> OperationLog:
        """
        功能：写入一条操作审计。默认不保存 request body。
        事务边界：只 add，由调用方 commit；业务 rollback 时成功日志一起撤销。
        """
        row = OperationLog(
            tenant_id=self.tenant_id,
            operator_user_id=operator_user_id,
            action=action,
            module=module,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            request_method=request_method,
            request_path=request_path,
            request_id=get_request_id(),
            result=result,
            error_code=error_code,
            description=description,
            extra_metadata=sanitize_payload(metadata) if metadata else None,
            occurred_at=datetime.now(),
        )
        self.repo.add(row)
        return row


def write_failed_operation(
    *,
    tenant_id: int | None,
    operator_user_id: int | None,
    action: str,
    module: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    resource_name: str | None = None,
    description: str | None = None,
    error_code: str | None = None,
) -> None:
    """业务事务已经 rollback 后，用独立 Session 留下 FAILED 审计。"""
    session = SessionLocal()
    try:
        OperationLogService(session, tenant_id).write(
            action=action,
            module=module,
            result=OperationResult.FAILED.value,
            operator_user_id=operator_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            description=description,
            error_code=error_code,
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def context_operator(context: TenantContext) -> tuple[int, int]:
    return context.tenant_id, context.user_id
