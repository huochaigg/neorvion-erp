"""统一事件写入。业务代码不要直接 session.add(SystemEvent(...))。

功能：规范化字段、脱敏 payload、在当前事务内写入 Outbox。
事务边界：只 add / flush，不 commit。主业务失败时事件一起 rollback。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.events import (
    EVENT_ID_PREFIX,
    EVENT_TYPE_TITLES,
    AggregateType,
    EventSource,
    EventStatus,
    EventType,
)
from app.core.request_id import get_request_id
from app.core.sanitize import sanitize_payload
from app.models.system_event import SystemEvent
from app.repositories.system_event import SystemEventRepository

OUTBOX_SESSION_KEY = "outbox_event_ids"


def new_event_id() -> str:
    return f"{EVENT_ID_PREFIX}{uuid.uuid4().hex}"


class EventPublisher:
    def __init__(self, session: Session, tenant_id: int | None) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repo = SystemEventRepository(session, tenant_id)

    def record(
        self,
        *,
        event_type: EventType | str,
        aggregate_type: AggregateType | str,
        aggregate_id: int | None = None,
        title: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        reference_type: str | None = None,
        reference_id: int | None = None,
        severity: str = "INFO",
        event_source: str = EventSource.ERP.value,
        operator_user_id: int | None = None,
    ) -> SystemEvent:
        """
        功能：在当前数据库事务内写入一条业务事件。
        参数：稳定 event_type / aggregate，以及必要快照 payload。
        返回：已加入 Session 的 SystemEvent，status=PENDING。
        异常：无业务校验异常；非法枚举由调用方保证。
        核心流程：生成 event_id → 脱敏 → add → 登记 session.info 供 commit 后入队。
        事务边界：不 commit。必须与订单确认、库存预占等写在同一事务。
        """
        type_code = str(event_type)
        event = SystemEvent(
            tenant_id=self.tenant_id,
            event_id=new_event_id(),
            event_type=type_code,
            event_source=str(event_source),
            aggregate_type=str(aggregate_type),
            aggregate_id=aggregate_id,
            reference_type=reference_type,
            reference_id=reference_id,
            severity=severity,
            title=title or EVENT_TYPE_TITLES.get(type_code, type_code),
            message=message,
            payload=sanitize_payload(payload) if payload else None,
            extra_metadata=sanitize_payload(
                {
                    **(metadata or {}),
                    **(
                        {"request_id": get_request_id()}
                        if get_request_id()
                        else {}
                    ),
                    **(
                        {"operator_user_id": operator_user_id}
                        if operator_user_id is not None
                        else {}
                    ),
                }
            )
            or None,
            status=EventStatus.PENDING.value,
            occurred_at=datetime.now(),
        )
        self.repo.add(event)
        pending: list[str] = self.session.info.setdefault(OUTBOX_SESSION_KEY, [])
        pending.append(event.event_id)
        return event
