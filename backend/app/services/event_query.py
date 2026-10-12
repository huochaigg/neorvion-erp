from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.system_event import SystemEvent
from app.repositories.system_event import SystemEventRepository
from app.schemas.system_event import SystemEventListOut, SystemEventOut


def event_out(row: SystemEvent) -> SystemEventOut:
    return SystemEventOut(
        id=row.id,
        event_id=row.event_id,
        event_type=row.event_type,
        event_source=row.event_source,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        reference_type=row.reference_type,
        reference_id=row.reference_id,
        severity=row.severity,
        title=row.title,
        message=row.message,
        payload=row.payload,
        metadata=row.extra_metadata,
        status=row.status,
        retry_count=row.retry_count,
        last_error=row.last_error,
        occurred_at=row.occurred_at,
        processed_at=row.processed_at,
        created_at=row.created_at,
    )


class EventQueryService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.repo = SystemEventRepository(session, context.tenant_id)

    def list_events(
        self,
        *,
        event_type: str | None = None,
        event_source: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: int | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
        severity: str | None = None,
        status: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SystemEventListOut:
        rows, total = self.repo.list_events(
            event_type=event_type,
            event_source=event_source,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            reference_type=reference_type,
            reference_id=reference_id,
            severity=severity,
            status=status,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )
        return SystemEventListOut(
            items=[event_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_event(self, event_id: str) -> SystemEventOut:
        row = self.repo.get_by_event_id(event_id)
        if row is None:
            raise AppError("事件不存在或不可访问", code=40700, status_code=404)
        return event_out(row)
