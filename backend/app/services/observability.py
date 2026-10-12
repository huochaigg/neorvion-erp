"""业务 Service 最小侵入接入事件与操作日志。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.events import AggregateType, EventType
from app.core.exceptions import AppError
from app.core.operations import OperationResult
from app.core.tenant import TenantContext
from app.models.system_event import SystemEvent
from app.services.event_publisher import EventPublisher
from app.services.operation_log import OperationLogService, write_failed_operation


def emit_event(
    session: Session,
    context: TenantContext,
    *,
    event_type: EventType | str,
    aggregate_type: AggregateType | str,
    aggregate_id: int | None,
    payload: dict[str, Any] | None = None,
    message: str | None = None,
    title: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    severity: str = "INFO",
    event_source: str = "ERP",
) -> SystemEvent:
    return EventPublisher(session, context.tenant_id).record(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        title=title,
        message=message,
        payload=payload,
        reference_type=reference_type,
        reference_id=reference_id,
        severity=severity,
        event_source=event_source,
        operator_user_id=context.user_id,
    )


def emit_operation(
    session: Session,
    context: TenantContext,
    *,
    action: str,
    module: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    resource_name: str | None = None,
    description: str | None = None,
) -> None:
    OperationLogService(session, context.tenant_id).write(
        action=action,
        module=module,
        result=OperationResult.SUCCESS.value,
        operator_user_id=context.user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        description=description,
    )


def rollback_with_failed_log(
    session: Session,
    context: TenantContext,
    exc: AppError,
    *,
    action: str,
    module: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    resource_name: str | None = None,
) -> None:
    session.rollback()
    write_failed_operation(
        tenant_id=context.tenant_id,
        operator_user_id=context.user_id,
        action=action,
        module=module,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        description=exc.message,
        error_code=str(exc.code),
    )
