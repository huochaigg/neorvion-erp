from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin


class AgentRun(TenantMixin, Base):
    __tablename__ = "copilot_agent_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_runs_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            [
                "copilot_conversations.tenant_id",
                "copilot_conversations.user_id",
                "copilot_conversations.id",
            ],
            ondelete="CASCADE",
            name="fk_copilot_agent_runs_conversation_owner",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["copilot_messages.tenant_id", "copilot_messages.id"],
            ondelete="CASCADE",
            name="fk_copilot_agent_runs_message",
        ),
        UniqueConstraint("tenant_id", "message_id", name="uq_copilot_agent_run_message"),
        Index("ix_copilot_agent_runs_owner_started", "tenant_id", "user_id", "started_at"),
        CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','DEGRADED')",
            name="ck_copilot_agent_run_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="PENDING")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="RUNNING")
    route_reason: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_duration_ms: Mapped[int | None] = mapped_column()
    error_code: Mapped[int | None] = mapped_column()
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class AgentTaskRun(TenantMixin, Base):
    __tablename__ = "copilot_agent_task_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_task_runs_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["copilot_agent_runs.tenant_id", "copilot_agent_runs.id"],
            ondelete="CASCADE",
            name="fk_copilot_agent_task_run_parent",
        ),
        UniqueConstraint("tenant_id", "agent_run_id", "task_id", name="uq_copilot_agent_task_key"),
        Index("ix_copilot_agent_tasks_parent", "tenant_id", "agent_run_id", "started_at"),
        CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','DEGRADED')",
            name="ck_copilot_agent_task_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="RUNNING")
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column()
    model_calls: Mapped[int] = mapped_column(nullable=False, server_default="0")
    tool_calls: Mapped[int] = mapped_column(nullable=False, server_default="0")
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    evidence_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    error_code: Mapped[int | None] = mapped_column()
