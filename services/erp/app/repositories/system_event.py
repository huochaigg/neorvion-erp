from datetime import datetime

from sqlalchemy import Select, func, or_, select

from app.models.system_event import SystemEvent
from app.repositories.base import BaseRepository


class SystemEventRepository(BaseRepository):
    def add(self, event: SystemEvent) -> SystemEvent:
        self.session.add(event)
        return event

    def get_by_event_id(self, event_id: str) -> SystemEvent | None:
        tenant_id = self.ensure_tenant()
        stmt = select(SystemEvent).where(
            SystemEvent.event_id == event_id,
            SystemEvent.tenant_id == tenant_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_pk(self, event_pk: int) -> SystemEvent | None:
        tenant_id = self.ensure_tenant()
        stmt = select(SystemEvent).where(
            SystemEvent.id == event_pk,
            SystemEvent.tenant_id == tenant_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def _filtered(
        self,
        *,
        event_type: str | None,
        event_source: str | None,
        aggregate_type: str | None,
        aggregate_id: int | None,
        reference_type: str | None,
        reference_id: int | None,
        severity: str | None,
        status: str | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        keyword: str | None,
    ) -> Select[SystemEvent]:
        tenant_id = self.ensure_tenant()
        stmt = select(SystemEvent).where(SystemEvent.tenant_id == tenant_id)
        if event_type:
            stmt = stmt.where(SystemEvent.event_type == event_type)
        if event_source:
            stmt = stmt.where(SystemEvent.event_source == event_source)
        if aggregate_type:
            stmt = stmt.where(SystemEvent.aggregate_type == aggregate_type)
        if aggregate_id is not None:
            stmt = stmt.where(SystemEvent.aggregate_id == aggregate_id)
        if reference_type:
            stmt = stmt.where(SystemEvent.reference_type == reference_type)
        if reference_id is not None:
            stmt = stmt.where(SystemEvent.reference_id == reference_id)
        if severity:
            stmt = stmt.where(SystemEvent.severity == severity)
        if status:
            stmt = stmt.where(SystemEvent.status == status)
        if occurred_from is not None:
            stmt = stmt.where(SystemEvent.occurred_at >= occurred_from)
        if occurred_to is not None:
            stmt = stmt.where(SystemEvent.occurred_at < occurred_to)
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(
                or_(
                    SystemEvent.title.like(like),
                    SystemEvent.message.like(like),
                    SystemEvent.event_id.like(like),
                )
            )
        return stmt

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
    ) -> tuple[list[SystemEvent], int]:
        filtered = self._filtered(
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
        )
        total = int(
            self.session.execute(select(func.count()).select_from(filtered.subquery())).scalar_one()
        )
        rows = list(
            self.session.scalars(
                filtered.order_by(SystemEvent.occurred_at.desc(), SystemEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return rows, total
