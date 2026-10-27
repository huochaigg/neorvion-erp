from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class InsightRule(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_insight_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_insight_rules_tenant"),
        UniqueConstraint("tenant_id", "name", name="uq_copilot_insight_rule_name"),
        Index("ix_insight_rules_due", "enabled", "next_run_at"),
        CheckConstraint("interval_minutes >= 15", name="ck_insight_rule_interval"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    detector_type: Mapped[str] = mapped_column(String(48), nullable=False)
    detector_version: Mapped[str] = mapped_column(String(24), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="Asia/Shanghai"
    )
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    severity_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3600")
    max_alerts_per_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class InsightRuleRevision(TenantMixin, Base):
    __tablename__ = "copilot_insight_rule_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "rule_id"],
            ["copilot_insight_rules.tenant_id", "copilot_insight_rules.id"],
            ondelete="CASCADE",
            name="fk_insight_revision_rule",
        ),
        UniqueConstraint("tenant_id", "rule_id", "revision", name="uq_insight_rule_revision"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    changed_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class InsightDetectionRun(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_insight_detection_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_insight_runs_tenant"),
        ForeignKeyConstraint(
            ["tenant_id", "rule_id"],
            ["copilot_insight_rules.tenant_id", "copilot_insight_rules.id"],
            ondelete="RESTRICT",
            name="fk_insight_run_rule",
        ),
        UniqueConstraint("tenant_id", "rule_id", "schedule_key", name="uq_insight_run_schedule"),
        Index("ix_insight_runs_worker", "status", "lease_until"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_by: Mapped[int | None] = mapped_column(BigInteger)
    schedule_key: Mapped[str] = mapped_column(String(96), nullable=False)
    detector_version: Mapped[str] = mapped_column(String(24), nullable=False)
    rule_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="QUEUED")
    detected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[int | None] = mapped_column(Integer)
    safe_error: Mapped[str | None] = mapped_column(String(255))
    lease_owner: Mapped[str | None] = mapped_column(String(96))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BusinessInsight(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_business_insights"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_business_insights_tenant"),
        ForeignKeyConstraint(
            ["tenant_id", "rule_id"],
            ["copilot_insight_rules.tenant_id", "copilot_insight_rules.id"],
            ondelete="RESTRICT",
            name="fk_business_insight_rule",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "detection_run_id"],
            ["copilot_insight_detection_runs.tenant_id", "copilot_insight_detection_runs.id"],
            ondelete="RESTRICT",
            name="fk_business_insight_run",
        ),
        UniqueConstraint(
            "tenant_id", "rule_id", "fingerprint", name="uq_business_insight_fingerprint"
        ),
        Index("ix_business_insights_status", "tenant_id", "status", "severity"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detection_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detector_type: Mapped[str] = mapped_column(String(48), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(48), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OPEN")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    analysis_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="NOT_REQUESTED"
    )
    ai_summary: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )


class InsightEvent(TenantMixin, Base):
    __tablename__ = "copilot_insight_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "insight_id"],
            ["copilot_business_insights.tenant_id", "copilot_business_insights.id"],
            ondelete="CASCADE",
            name="fk_insight_event_insight",
        ),
        Index("ix_insight_events_timeline", "tenant_id", "insight_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    insight_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    safe_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class InsightNotification(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_insight_notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "insight_id"],
            ["copilot_business_insights.tenant_id", "copilot_business_insights.id"],
            ondelete="CASCADE",
            name="fk_insight_notification_insight",
        ),
        UniqueConstraint(
            "tenant_id", "insight_id", "recipient_user_id", name="uq_insight_notification_recipient"
        ),
        Index("ix_insight_notifications_unread", "tenant_id", "recipient_user_id", "read_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    insight_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recipient_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    safe_body: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="DELIVERED"
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
