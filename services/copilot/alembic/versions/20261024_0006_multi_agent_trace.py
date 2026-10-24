"""add V8 multi-agent trace

Revision ID: 20261024_0006
Revises: 20261024_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0006"
down_revision: str | None = "20261024_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copilot_agent_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("graph_type", sa.String(32), server_default="PENDING", nullable=False),
        sa.Column("status", sa.String(16), server_default="RUNNING", nullable=False),
        sa.Column("route_reason", sa.String(255)),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("total_duration_ms", sa.Integer()),
        sa.Column("error_code", sa.Integer()),
        sa.Column("usage", postgresql.JSONB()),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','DEGRADED')",
            name="ck_copilot_agent_run_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            [
                "copilot_conversations.tenant_id",
                "copilot_conversations.user_id",
                "copilot_conversations.id",
            ],
            ondelete="CASCADE",
            name="fk_copilot_agent_runs_conversation_owner",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["copilot_messages.tenant_id", "copilot_messages.id"],
            ondelete="CASCADE",
            name="fk_copilot_agent_runs_message",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_runs_tenant_id"),
        sa.UniqueConstraint("tenant_id", "message_id", name="uq_copilot_agent_run_message"),
    )
    op.create_index(
        "ix_copilot_agent_runs_owner_started",
        "copilot_agent_runs",
        ["tenant_id", "user_id", "started_at"],
    )
    op.create_table(
        "copilot_agent_task_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_run_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("task_id", sa.String(96), nullable=False),
        sa.Column("status", sa.String(16), server_default="RUNNING", nullable=False),
        sa.Column("input_summary", sa.Text()),
        sa.Column("output_summary", sa.Text()),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("model_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tool_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("usage", postgresql.JSONB()),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.Integer()),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','DEGRADED')",
            name="ck_copilot_agent_task_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["copilot_agent_runs.tenant_id", "copilot_agent_runs.id"],
            ondelete="CASCADE",
            name="fk_copilot_agent_task_run_parent",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_agent_task_runs_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "agent_run_id", "task_id", name="uq_copilot_agent_task_key"
        ),
    )
    op.create_index(
        "ix_copilot_agent_tasks_parent",
        "copilot_agent_task_runs",
        ["tenant_id", "agent_run_id", "started_at"],
    )
    op.add_column("copilot_tool_runs", sa.Column("agent_task_id", sa.String(96)))
    op.add_column("copilot_evidences", sa.Column("source_agent", sa.String(64)))
    op.add_column("copilot_evidences", sa.Column("agent_task_id", sa.String(96)))


def downgrade() -> None:
    op.drop_column("copilot_evidences", "agent_task_id")
    op.drop_column("copilot_evidences", "source_agent")
    op.drop_column("copilot_tool_runs", "agent_task_id")
    op.drop_index("ix_copilot_agent_tasks_parent", table_name="copilot_agent_task_runs")
    op.drop_table("copilot_agent_task_runs")
    op.drop_index("ix_copilot_agent_runs_owner_started", table_name="copilot_agent_runs")
    op.drop_table("copilot_agent_runs")
