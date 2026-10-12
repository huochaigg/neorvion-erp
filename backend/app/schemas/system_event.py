from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SystemEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str = Field(..., description="事件全局唯一标识，用于异步消费去重和跨系统追踪")
    event_type: str = Field(..., description="稳定事件类型，例如 SALES_ORDER_CONFIRMED")
    event_source: str = Field(..., description="事件由哪个子系统产生：ERP / SYSTEM / TASK")
    aggregate_type: str = Field(
        ..., description="事件所属业务聚合类型，例如 SALES_ORDER、PURCHASE_ORDER、INVENTORY"
    )
    aggregate_id: int | None = Field(None, description="主要业务聚合主键")
    reference_type: str | None = Field(None, description="补充关联对象类型")
    reference_id: int | None = Field(None, description="关联业务对象主键，用于跳转原单据")
    severity: str = Field(..., description="INFO / WARNING / ERROR / CRITICAL")
    title: str
    message: str | None = None
    payload: dict[str, Any] | None = Field(None, description="事件必要快照，不含密码和令牌")
    metadata: dict[str, Any] | None = Field(None, description="扩展追踪信息，例如 request_id")
    status: str = Field(
        ..., description="Outbox 处理状态 PENDING / PROCESSING / PROCESSED / FAILED"
    )
    retry_count: int
    last_error: str | None = None
    occurred_at: datetime
    processed_at: datetime | None = None
    created_at: datetime


class SystemEventListOut(BaseModel):
    items: list[SystemEventOut]
    total: int
    page: int
    page_size: int
