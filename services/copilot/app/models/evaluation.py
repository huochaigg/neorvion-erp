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


class AgentEvaluationDataset(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_agent_evaluation_datasets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_eval_datasets_tenant"),
        UniqueConstraint("tenant_id", "user_id", "name", name="uq_copilot_agent_eval_dataset_name"),
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','ARCHIVED')", name="ck_agent_eval_dataset_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="DRAFT")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AgentEvaluationCase(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_agent_evaluation_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_eval_cases_tenant"),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["copilot_agent_evaluation_datasets.tenant_id", "copilot_agent_evaluation_datasets.id"],
            ondelete="CASCADE",
            name="fk_agent_eval_case_dataset",
        ),
        UniqueConstraint(
            "tenant_id", "dataset_id", "external_key", name="uq_agent_eval_case_external_key"
        ),
        Index("ix_agent_eval_cases_dataset", "tenant_id", "dataset_id", "status"),
        CheckConstraint(
            "status IN ('READY','NEEDS_REVIEW','DISABLED')", name="ck_agent_eval_case_status"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    external_key: Mapped[str] = mapped_column(String(96), nullable=False)
    case_type: Mapped[str] = mapped_column(String(64), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2")
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_behavior: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expected_tools: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    expected_arguments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    expected_evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    expected_answer_assertions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    forbidden_actions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    required_permissions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    scenario_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="NEEDS_REVIEW")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AgentEvaluationDatasetVersion(TenantMixin, Base):
    __tablename__ = "copilot_agent_evaluation_dataset_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_eval_versions_tenant"),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["copilot_agent_evaluation_datasets.tenant_id", "copilot_agent_evaluation_datasets.id"],
            ondelete="RESTRICT",
            name="fk_agent_eval_version_dataset",
        ),
        UniqueConstraint(
            "tenant_id", "dataset_id", "version", name="uq_agent_eval_dataset_version"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False)
    frozen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    frozen_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AgentEvaluationRun(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_agent_evaluation_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_eval_runs_tenant"),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_version_id"],
            [
                "copilot_agent_evaluation_dataset_versions.tenant_id",
                "copilot_agent_evaluation_dataset_versions.id",
            ],
            ondelete="RESTRICT",
            name="fk_agent_eval_run_version",
        ),
        UniqueConstraint(
            "tenant_id", "user_id", "idempotency_key", name="uq_agent_eval_run_idempotency"
        ),
        Index("ix_agent_eval_runs_worker", "status", "lease_until"),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','PAUSING','PAUSED','SUCCEEDED','PARTIAL_FAILED','FAILED','CANCELLED')",
            name="ck_agent_eval_run_status",
        ),
        CheckConstraint("mode IN ('SINGLE','MULTI','AUTO')", name="ck_agent_eval_run_mode"),
        CheckConstraint("execution_kind IN ('REPLAY','LIVE')", name="ck_agent_eval_execution_kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dataset_version_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    comparison_group: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(96), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    execution_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="REPLAY")
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    environment_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="QUEUED")
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_cases: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    token_budget: Mapped[int | None] = mapped_column(BigInteger)
    cost_budget: Mapped[float | None] = mapped_column(Numeric(18, 8))
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    lease_owner: Mapped[str | None] = mapped_column(String(96))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pause_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentEvaluationCaseRun(TenantMixin, Base):
    __tablename__ = "copilot_agent_evaluation_case_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_eval_case_runs_tenant"),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["copilot_agent_evaluation_runs.tenant_id", "copilot_agent_evaluation_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_eval_case_run_parent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["copilot_agent_runs.tenant_id", "copilot_agent_runs.id"],
            ondelete="RESTRICT",
            name="fk_agent_eval_case_run_agent_trace",
        ),
        UniqueConstraint("tenant_id", "run_id", "case_key", name="uq_agent_eval_case_run_key"),
        Index("ix_agent_eval_case_runs_run", "tenant_id", "run_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    case_key: Mapped[str] = mapped_column(String(96), nullable=False)
    agent_run_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    task_outcome: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="INDETERMINATE"
    )
    actual_answer: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    assertion_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    judge_model: Mapped[str | None] = mapped_column(String(128))
    judge_prompt_version: Mapped[str | None] = mapped_column(String(64))
    judge_feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    judge_confidence: Mapped[float | None] = mapped_column(Numeric(6, 5))
    human_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class AgentEvaluationRunEvent(TenantMixin, Base):
    __tablename__ = "copilot_agent_evaluation_run_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["copilot_agent_evaluation_runs.tenant_id", "copilot_agent_evaluation_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_eval_event_run",
        ),
        Index("ix_agent_eval_events_run", "tenant_id", "run_id", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ModelCall(TenantMixin, Base):
    __tablename__ = "copilot_model_calls"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_model_calls_tenant"),
        UniqueConstraint("tenant_id", "model_call_id", name="uq_copilot_model_call_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["copilot_agent_runs.tenant_id", "copilot_agent_runs.id"],
            ondelete="CASCADE",
            name="fk_model_call_agent_run",
        ),
        Index("ix_copilot_model_calls_agent_run", "tenant_id", "agent_run_id", "started_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_run_id: Mapped[int | None] = mapped_column(BigInteger)
    agent_task_id: Mapped[str | None] = mapped_column(String(96))
    model_call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    cached_tokens: Mapped[int | None] = mapped_column(BigInteger)
    reasoning_tokens: Mapped[int | None] = mapped_column(BigInteger)
    finish_reason: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[int | None] = mapped_column(Integer)
    usage_source: Mapped[str] = mapped_column(String(32), nullable=False, server_default="UNKNOWN")
    provider_reported_cost: Mapped[float | None] = mapped_column(Numeric(18, 8))
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(18, 8))
    currency: Mapped[str | None] = mapped_column(String(8))
    pricing_version: Mapped[str | None] = mapped_column(String(64))


class ModelPricing(TenantMixin, Base):
    __tablename__ = "copilot_model_pricing"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_copilot_model_pricing_tenant"),
        UniqueConstraint(
            "tenant_id", "provider", "model", "pricing_version", name="uq_model_pricing_version"
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_price: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    output_price: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    unit_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1000000")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class AgentEvaluationComparison(TimestampMixin, TenantMixin, Base):
    __tablename__ = "copilot_agent_evaluation_comparisons"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_eval_comparisons_tenant"),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "baseline_run_id",
            "candidate_run_id",
            name="uq_agent_eval_comparison_pair",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "baseline_run_id"],
            ["copilot_agent_evaluation_runs.tenant_id", "copilot_agent_evaluation_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_eval_comparison_baseline",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "candidate_run_id"],
            ["copilot_agent_evaluation_runs.tenant_id", "copilot_agent_evaluation_runs.id"],
            ondelete="CASCADE",
            name="fk_agent_eval_comparison_candidate",
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    baseline_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candidate_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    comparable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    incomparable_reason: Mapped[str | None] = mapped_column(Text)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
