"""系统事件 / Outbox。与主业务同一事务写入，再由 Worker 消费。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemEvent(Base):
    """业务事件存储 + 轻量 Outbox。tenant_id 为空表示系统级事件，普通租户不可见。"""

    __tablename__ = "system_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_system_events_event_id"),
        Index("ix_system_events_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_system_events_tenant_type_occurred", "tenant_id", "event_type", "occurred_at"),
        Index("ix_system_events_tenant_aggregate", "tenant_id", "aggregate_type", "aggregate_id"),
        Index("ix_system_events_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="事件全局唯一标识，用于异步消费去重和跨系统追踪",
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="稳定事件类型，例如 SALES_ORDER_CONFIRMED",
    )
    event_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ERP",
        comment="事件由哪个子系统产生：ERP / SYSTEM / TASK",
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="事件所属业务聚合类型，例如 SALES_ORDER、PURCHASE_ORDER、INVENTORY",
    )
    aggregate_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="主要业务聚合主键，用于查询某张单据发生过什么",
    )
    reference_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="补充关联对象类型，语义与库存流水 reference_type 一致",
    )
    reference_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="关联业务对象主键，用于从事件详情跳转到原业务单据",
    )
    severity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="INFO",
        comment="INFO 普通业务；WARNING 库存不足；ERROR 任务失败；CRITICAL 严重异常",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="事件必要快照 JSON，禁止包含密码、令牌和密钥",
    )
    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="扩展追踪信息，例如 request_id、operator_user_id",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="PENDING",
        comment="Outbox 处理状态：PENDING / PROCESSING / PROCESSED / FAILED",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Outbox 消费失败已重试次数，上限 3",
    )
    last_error: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="最近一次消费失败的简要原因，不存完整 traceback",
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="下次允许 Outbox 重试的时间；空表示可立即领取",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
