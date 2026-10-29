from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class AIModelProvider(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_ai_model_providers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ai_provider_tenant"),
        UniqueConstraint("tenant_id", "code", name="uq_ai_provider_code"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret_env_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DISABLED")
    data_region: Mapped[str] = mapped_column(String(32), nullable=False, server_default="UNKNOWN")
    last_probe_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="UNKNOWN"
    )
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AIModelDefinition(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_ai_models"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ai_model_tenant"),
        UniqueConstraint("tenant_id", "provider_id", "model_name", name="uq_ai_model_name"),
        ForeignKeyConstraint(
            ["tenant_id", "provider_id"],
            ["copilot_ai_model_providers.tenant_id", "copilot_ai_model_providers.id"],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    purposes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    supports_tools: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    context_window: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    pricing_version: Mapped[str | None] = mapped_column(String(64))
    input_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    output_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    currency: Mapped[str | None] = mapped_column(String(8))
    unit_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1000000")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AIGovernancePolicy(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_ai_governance_policies"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_ai_policy_tenant"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    allowed_provider_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    allowed_model_names: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    allowed_agents: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    multi_agent_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    insight_analysis_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    live_evaluation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    max_context_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="6000")
    trace_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90")
    conversation_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="365"
    )
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class TenantAIQuota(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_tenant_ai_quotas"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_ai_quota_tenant"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    requests_per_day: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    monthly_token_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="1000000"
    )
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="CNY")
    max_concurrent_agents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    max_concurrent_evaluations: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    insight_monthly_token_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="200000"
    )
    max_tool_calls_per_request: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="8"
    )
    max_execution_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    warning_threshold_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="80"
    )
    hard_limit: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AIGovernanceAudit(TenantMixin, Base):
    __tablename__ = "copilot_ai_governance_audits"
    __table_args__ = (Index("ix_ai_governance_audit_query", "tenant_id", "created_at", "action"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    safe_detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class AIRetentionRun(TenantMixin, Base):
    __tablename__ = "copilot_ai_retention_runs"
    __table_args__ = (Index("ix_ai_retention_runs_tenant_created", "tenant_id", "created_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    requested_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    cutoff_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    affected_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    safe_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
