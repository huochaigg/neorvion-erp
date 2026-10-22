from datetime import datetime

from neorvion_db import PrivilegedOperation, privileged_option
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.events import EventStatus
from app.models.system_event import SystemEvent
from app.repositories.base import BaseRepository


class SystemEventRepository(BaseRepository):
    def add(self, event: SystemEvent) -> SystemEvent:
        self.session.add(event)
        return event

    def get_by_event_id(self, event_id: str) -> SystemEvent | None:
        stmt = select(SystemEvent).where(SystemEvent.event_id == event_id)
        if self.tenant_id is not None:
            stmt = stmt.where(SystemEvent.tenant_id == self.tenant_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_pk(self, event_pk: int) -> SystemEvent | None:
        stmt = select(SystemEvent).where(SystemEvent.id == event_pk)
        if self.tenant_id is not None:
            stmt = stmt.where(SystemEvent.tenant_id == self.tenant_id)
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
        stmt = select(SystemEvent)
        if self.tenant_id is not None:
            stmt = stmt.where(SystemEvent.tenant_id == self.tenant_id)
        else:
            stmt = stmt.where(SystemEvent.tenant_id.is_(None))
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

    def claim_pending(self, limit: int = 20) -> list[SystemEvent]:
        """
        功能：并发安全领取待处理 Outbox 事件。
        核心流程：SELECT ... FOR UPDATE SKIP LOCKED，避免多个 Worker 处理同一行。
        事务边界：调用方负责随后改状态并 commit。
        """
        now = datetime.now()
        stmt = (
            select(SystemEvent)
            .where(
                SystemEvent.status == EventStatus.PENDING.value,
                or_(SystemEvent.next_retry_at.is_(None), SystemEvent.next_retry_at <= now),
            )
            .order_by(SystemEvent.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
            .execution_options(**privileged_option(PrivilegedOperation.OUTBOX_SCAN))
        )
        return list(self.session.execute(stmt).scalars())


def claim_pending_events(session: Session, limit: int = 20) -> list[SystemEvent]:
    return SystemEventRepository(session, None).claim_pending(limit)
