"""V11 enterprise AI governance.

Revision ID: 20261027_0011
Revises: 7f803d545046
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261027_0011"
down_revision: str | None = "7f803d545046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_columns() -> list[sa.Column]:
    return [sa.Column("tenant_id", sa.BigInteger(), nullable=False)]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # V10 历史迁移曾直接引用当前 ORM metadata；从空库回放时，
    # 新版 ORM 可能已提前创建本列。IF NOT EXISTS 让新环境和已有 V10 环境
    # 都能安全升级，且不触及任何业务数据。
    op.execute(
        "ALTER TABLE copilot_insight_detection_runs "
        "ADD COLUMN IF NOT EXISTS attempt_count INTEGER DEFAULT 0 NOT NULL"
    )
    op.create_table(
        "copilot_ai_model_providers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        *_tenant_columns(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("secret_env_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), server_default="DISABLED", nullable=False),
        sa.Column("data_region", sa.String(32), server_default="UNKNOWN", nullable=False),
        sa.Column("last_probe_status", sa.String(20), server_default="UNKNOWN", nullable=False),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ai_provider_tenant"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_ai_provider_code"),
    )
    op.create_table(
        "copilot_ai_models",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        *_tenant_columns(),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("purposes", postgresql.JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_tools", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("pricing_version", sa.String(64), nullable=True),
        sa.Column("input_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("output_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("unit_tokens", sa.BigInteger(), server_default="1000000", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "provider_id"],
            ["copilot_ai_model_providers.tenant_id", "copilot_ai_model_providers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ai_model_tenant"),
        sa.UniqueConstraint("tenant_id", "provider_id", "model_name", name="uq_ai_model_name"),
    )
    op.create_table(
        "copilot_ai_governance_policies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        *_tenant_columns(),
        sa.Column(
            "allowed_provider_codes", postgresql.JSONB(), server_default="[]", nullable=False
        ),
        sa.Column("allowed_model_names", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("allowed_agents", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("allowed_tools", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column(
            "multi_agent_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "insight_analysis_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "live_evaluation_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("max_context_tokens", sa.Integer(), server_default="6000", nullable=False),
        sa.Column("trace_retention_days", sa.Integer(), server_default="90", nullable=False),
        sa.Column(
            "conversation_retention_days", sa.Integer(), server_default="365", nullable=False
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_ai_policy_tenant"),
    )
    op.create_table(
        "copilot_tenant_ai_quotas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        *_tenant_columns(),
        sa.Column("requests_per_minute", sa.Integer(), server_default="30", nullable=False),
        sa.Column("requests_per_day", sa.Integer(), server_default="1000", nullable=False),
        sa.Column("monthly_token_limit", sa.BigInteger(), server_default="1000000", nullable=False),
        sa.Column("monthly_budget", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(8), server_default="CNY", nullable=False),
        sa.Column("max_concurrent_agents", sa.Integer(), server_default="3", nullable=False),
        sa.Column("max_concurrent_evaluations", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "insight_monthly_token_limit", sa.BigInteger(), server_default="200000", nullable=False
        ),
        sa.Column("max_tool_calls_per_request", sa.Integer(), server_default="8", nullable=False),
        sa.Column("max_execution_seconds", sa.Integer(), server_default="60", nullable=False),
        sa.Column("warning_threshold_percent", sa.Integer(), server_default="80", nullable=False),
        sa.Column("hard_limit", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_ai_quota_tenant"),
    )
    op.create_table(
        "copilot_ai_governance_audits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        *_tenant_columns(),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("safe_detail", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("request_id", sa.String(64), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_governance_audit_query",
        "copilot_ai_governance_audits",
        ["tenant_id", "created_at", "action"],
    )
    op.create_table(
        "copilot_ai_retention_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        *_tenant_columns(),
        sa.Column("requested_by", sa.BigInteger(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("cutoff_summary", postgresql.JSONB(), nullable=False),
        sa.Column("affected_summary", postgresql.JSONB(), nullable=False),
        sa.Column("safe_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_retention_runs_tenant_created",
        "copilot_ai_retention_runs",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("copilot_ai_retention_runs")
    op.drop_table("copilot_ai_governance_audits")
    op.drop_table("copilot_tenant_ai_quotas")
    op.drop_table("copilot_ai_governance_policies")
    op.drop_table("copilot_ai_models")
    op.drop_table("copilot_ai_model_providers")
    op.drop_column("copilot_insight_detection_runs", "attempt_count")
