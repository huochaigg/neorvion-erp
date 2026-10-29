"""V12 controlled MCP and Skills ecosystem.

Revision ID: 20261028_0012
Revises: 20261027_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261028_0012"
down_revision: str | None = "20261027_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    ]


def upgrade() -> None:
    op.drop_constraint("ck_copilot_evidences_source", "copilot_evidences", type_="check")
    op.create_check_constraint(
        "ck_copilot_evidences_source",
        "copilot_evidences",
        "source_type IN ('ERP', 'KNOWLEDGE', 'MCP')",
    )
    op.create_table(
        "copilot_mcp_servers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("server_key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("scope_type", sa.String(16), server_default="TENANT", nullable=False),
        sa.Column(
            "transport_type", sa.String(32), server_default="STREAMABLE_HTTP", nullable=False
        ),
        sa.Column("endpoint", sa.String(500), nullable=False),
        sa.Column("authentication_type", sa.String(24), server_default="NONE", nullable=False),
        sa.Column("credential_reference", sa.String(128), nullable=True),
        sa.Column("allowed_tools", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("denied_tools", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("allowed_resources", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default="10", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="1", nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), server_default="2", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "approval_status", sa.String(24), server_default="PENDING_APPROVAL", nullable=False
        ),
        sa.Column("health_status", sa.String(24), server_default="UNKNOWN", nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("configuration_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mcp_server_tenant"),
        sa.UniqueConstraint("tenant_id", "server_key", name="uq_mcp_server_key"),
    )
    op.create_index(
        "ix_mcp_server_status",
        "copilot_mcp_servers",
        ["tenant_id", "enabled", "approval_status"],
    )
    op.create_table(
        "copilot_mcp_tool_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("qualified_name", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("schema_hash", sa.String(64), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("required_permissions", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("resource_requirements", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("allowed_agents", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("risk_level", sa.String(24), server_default="READ_ONLY", nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default="10", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "approval_status", sa.String(24), server_default="PENDING_APPROVAL", nullable=False
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "server_id"],
            ["copilot_mcp_servers.tenant_id", "copilot_mcp_servers.id"],
            ondelete="RESTRICT",
            name="fk_mcp_tool_server",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "server_id", "tool_name", "schema_hash", name="uq_mcp_tool_schema"
        ),
    )
    op.create_index(
        "ix_mcp_tool_active",
        "copilot_mcp_tool_versions",
        ["tenant_id", "enabled", "approval_status"],
    )
    op.create_table(
        "copilot_skills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "approval_status", sa.String(24), server_default="PENDING_APPROVAL", nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_skill_tenant"),
        sa.UniqueConstraint("tenant_id", "skill_key", name="uq_skill_key"),
    )
    op.create_table(
        "copilot_skill_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False),
        sa.Column("allowed_agents", postgresql.JSONB(), nullable=False),
        sa.Column("required_permissions", postgresql.JSONB(), nullable=False),
        sa.Column("allowed_tools", postgresql.JSONB(), nullable=False),
        sa.Column("required_evidence", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("risk_level", sa.String(24), server_default="READ_ONLY", nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default="30", nullable=False),
        sa.Column("token_budget", sa.Integer(), server_default="3000", nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "approval_status", sa.String(24), server_default="PENDING_APPROVAL", nullable=False
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "skill_id"],
            ["copilot_skills.tenant_id", "copilot_skills.id"],
            ondelete="RESTRICT",
            name="fk_skill_version_skill",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "skill_id", "version", name="uq_skill_version"),
    )
    op.create_table(
        "copilot_skill_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_version", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("status", sa.String(24), server_default="CREATED", nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("output_snapshot", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("safe_error", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "skill_id"],
            ["copilot_skills.tenant_id", "copilot_skills.id"],
            ondelete="RESTRICT",
            name="fk_skill_run_skill",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", "idempotency_key", name="uq_skill_run_key"),
    )
    op.create_index(
        "ix_skill_run_status", "copilot_skill_runs", ["tenant_id", "status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_skill_run_status", table_name="copilot_skill_runs")
    op.drop_table("copilot_skill_runs")
    op.drop_table("copilot_skill_versions")
    op.drop_table("copilot_skills")
    op.drop_index("ix_mcp_tool_active", table_name="copilot_mcp_tool_versions")
    op.drop_table("copilot_mcp_tool_versions")
    op.drop_index("ix_mcp_server_status", table_name="copilot_mcp_servers")
    op.drop_table("copilot_mcp_servers")
    op.drop_constraint("ck_copilot_evidences_source", "copilot_evidences", type_="check")
    op.create_check_constraint(
        "ck_copilot_evidences_source",
        "copilot_evidences",
        "source_type IN ('ERP', 'KNOWLEDGE')",
    )
