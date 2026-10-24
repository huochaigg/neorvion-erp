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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class WorkflowInstance(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_workflow_instances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            [
                "copilot_conversations.tenant_id",
                "copilot_conversations.user_id",
                "copilot_conversations.id",
            ],
            ondelete="RESTRICT",
            name="fk_copilot_workflow_conversation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            ["copilot_action_proposals.tenant_id", "copilot_action_proposals.id"],
            ondelete="RESTRICT",
            name="fk_copilot_workflow_proposal",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["copilot_action_executions.tenant_id", "copilot_action_executions.id"],
            ondelete="RESTRICT",
            name="fk_copilot_workflow_execution",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_copilot_workflow_instances_tenant_id"),
        UniqueConstraint(
            "tenant_id", "user_id", "idempotency_key", name="uq_copilot_workflow_start_idempotency"
        ),
        CheckConstraint(
            "status IN ('CREATED','QUEUED','RUNNING','WAITING_INPUT','WAITING_CONFIRMATION','WAITING_APPROVAL','RECONCILING','PAUSED','SUCCEEDED','FAILED','CANCELLED','EXPIRED','NEEDS_MANUAL_INTERVENTION')",
            name="ck_copilot_workflow_status",
        ),
        Index("ix_copilot_workflows_owner_updated", "tenant_id", "user_id", "updated_at"),
        Index("ix_copilot_workflows_worker", "status", "lease_until"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger)
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_step: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_thread_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    proposal_id: Mapped[int | None] = mapped_column(BigInteger)
    execution_id: Mapped[int | None] = mapped_column(BigInteger)
    lease_owner: Mapped[str | None] = mapped_column(String(96))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_attempts: Mapped[int] = mapped_column(nullable=False, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowStep(TenantMixin, Base):
    __tablename__ = "copilot_workflow_steps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "workflow_id"],
            ["copilot_workflow_instances.tenant_id", "copilot_workflow_instances.id"],
            ondelete="CASCADE",
            name="fk_copilot_workflow_steps_workflow",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_copilot_workflow_steps_tenant_id"),
        UniqueConstraint(
            "tenant_id", "workflow_id", "step_key", name="uq_copilot_workflow_step_key"
        ),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','WAITING','SUCCEEDED','FAILED','SKIPPED','CANCELLED','UNKNOWN')",
            name="ck_copilot_workflow_step_status",
        ),
        Index("ix_copilot_workflow_steps_workflow", "tenant_id", "workflow_id", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PENDING")
    attempt_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class WorkflowEvent(TenantMixin, Base):
    __tablename__ = "copilot_workflow_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "workflow_id"],
            ["copilot_workflow_instances.tenant_id", "copilot_workflow_instances.id"],
            ondelete="CASCADE",
            name="fk_copilot_workflow_events_workflow",
        ),
        Index("ix_copilot_workflow_events_workflow", "tenant_id", "workflow_id", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class WorkflowStepAttempt(TenantMixin, Base):
    __tablename__ = "copilot_workflow_step_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "step_id"],
            ["copilot_workflow_steps.tenant_id", "copilot_workflow_steps.id"],
            ondelete="CASCADE",
            name="fk_copilot_workflow_attempts_step",
        ),
        UniqueConstraint(
            "tenant_id", "step_id", "attempt_no", name="uq_copilot_workflow_step_attempt"
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    step_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempt_no: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
