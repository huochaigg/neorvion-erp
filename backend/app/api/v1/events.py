from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import EventReadContext
from app.schemas.common import ApiResponse, ok
from app.schemas.system_event import SystemEventListOut, SystemEventOut
from app.services.event_query import EventQueryService

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=ApiResponse[SystemEventListOut], summary="事件列表")
def list_events(
    context: EventReadContext,
    session: DbSession,
    event_type: str | None = Query(default=None, max_length=64),
    event_source: str | None = Query(default=None, max_length=32),
    aggregate_type: str | None = Query(default=None, max_length=32),
    aggregate_id: int | None = Query(default=None, gt=0),
    reference_type: str | None = Query(default=None, max_length=32),
    reference_id: int | None = Query(default=None, gt=0),
    severity: str | None = Query(default=None, max_length=16),
    status: str | None = Query(default=None, max_length=16),
    occurred_from: Annotated[datetime | None, Query()] = None,
    occurred_to: Annotated[datetime | None, Query()] = None,
    keyword: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[SystemEventListOut]:
    return ok(
        EventQueryService(session, context).list_events(
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
    )


@router.get("/{event_id}", response_model=ApiResponse[SystemEventOut], summary="事件详情")
def get_event(
    event_id: str,
    context: EventReadContext,
    session: DbSession,
) -> ApiResponse[SystemEventOut]:
    return ok(EventQueryService(session, context).get_event(event_id))
