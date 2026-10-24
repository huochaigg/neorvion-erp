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


class ActionExecution(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_action_executions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            ["copilot_action_proposals.tenant_id", "copilot_action_proposals.id"],
            ondelete="RESTRICT",
            name="fk_action_execution_proposal",
        ),
        UniqueConstraint(
            "tenant_id", "proposal_id", "proposal_revision", name="uq_action_execution_revision"
        ),
        UniqueConstraint("tenant_id", "execution_key", name="uq_action_execution_key"),
        UniqueConstraint(
            "tenant_id", "user_id", "client_request_id", name="uq_action_execution_client_request"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_action_execution_tenant_id"),
        CheckConstraint(
            "status IN ('PENDING_CONFIRMATION','WAITING_APPROVAL','APPROVED','EXECUTING','SUCCEEDED','FAILED','UNKNOWN','RECONCILING','REJECTED','CANCELLED','EXPIRED')",
            name="ck_action_execution_status",
        ),
        Index("ix_action_execution_owner_created", "tenant_id", "user_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    proposal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    proposal_revision: Mapped[int] = mapped_column(nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_key: Mapped[str] = mapped_column(String(128), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    confirmation_nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_id: Mapped[int | None] = mapped_column(BigInteger)
    erp_resource_type: Mapped[str | None] = mapped_column(String(40))
    erp_resource_id: Mapped[int | None] = mapped_column(BigInteger)
    erp_resource_no: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionApproval(TenantMixin, Base):
    __tablename__ = "copilot_action_approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["copilot_action_executions.tenant_id", "copilot_action_executions.id"],
            ondelete="RESTRICT",
            name="fk_action_approval_execution",
        ),
        UniqueConstraint("tenant_id", "execution_id", name="uq_action_approval_execution"),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','EXPIRED','REVOKED')",
            name="ck_action_approval_status",
        ),
        Index("ix_action_approval_queue", "tenant_id", "status", "requested_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    proposal_revision: Mapped[int] = mapped_column(nullable=False)
    execution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    applicant_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    approver_user_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(16))
    decision_reason: Mapped[str | None] = mapped_column(String(500))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActionExecutionAttempt(TenantMixin, Base):
    __tablename__ = "copilot_action_execution_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["copilot_action_executions.tenant_id", "copilot_action_executions.id"],
            ondelete="CASCADE",
            name="fk_action_attempt_execution",
        ),
        UniqueConstraint("tenant_id", "execution_id", "attempt_no", name="uq_action_attempt_no"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempt_no: Mapped[int] = mapped_column(nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    erp_request_id: Mapped[str | None] = mapped_column(String(128))


class ActionAuditEvent(TenantMixin, Base):
    __tablename__ = "copilot_action_audit_events"
    __table_args__ = (
        Index("ix_action_audit_execution", "tenant_id", "execution_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    proposal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    execution_id: Mapped[int | None] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ActionGraphCheckpoint(TenantMixin, Base):
    """执行图的持久化业务检查点；不包含 JWT、API Key 或其他凭证。"""

    __tablename__ = "copilot_action_graph_checkpoints"
    __table_args__ = (
        UniqueConstraint("tenant_id", "execution_id", name="uq_action_graph_checkpoint"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    node: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
