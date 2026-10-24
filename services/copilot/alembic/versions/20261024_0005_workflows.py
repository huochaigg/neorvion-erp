"""add durable workflow state

Revision ID: 20261024_0005
Revises: 20261024_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0005"
down_revision: str | None = "20261024_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copilot_workflow_instances",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger()),
        sa.Column("workflow_type", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_step", sa.String(64), nullable=False),
        sa.Column("graph_thread_id", sa.String(96), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("result_summary", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("proposal_id", sa.BigInteger()),
        sa.Column("execution_id", sa.BigInteger()),
        sa.Column("lease_owner", sa.String(96)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("run_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
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
        sa.CheckConstraint(
            "status IN ('CREATED','QUEUED','RUNNING','WAITING_INPUT','WAITING_CONFIRMATION',"
            "'WAITING_APPROVAL','RECONCILING','PAUSED','SUCCEEDED','FAILED','CANCELLED',"
            "'EXPIRED','NEEDS_MANUAL_INTERVENTION')",
            name="ck_copilot_workflow_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            [
                "copilot_conversations.tenant_id",
                "copilot_conversations.user_id",
                "copilot_conversations.id",
            ],
            ondelete="RESTRICT",
            name="fk_copilot_workflow_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            ["copilot_action_proposals.tenant_id", "copilot_action_proposals.id"],
            ondelete="RESTRICT",
            name="fk_copilot_workflow_proposal",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["copilot_action_executions.tenant_id", "copilot_action_executions.id"],
            ondelete="RESTRICT",
            name="fk_copilot_workflow_execution",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_thread_id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_workflow_instances_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "idempotency_key", name="uq_copilot_workflow_start_idempotency"
        ),
    )
    op.create_index(
        "ix_copilot_workflows_owner_updated",
        "copilot_workflow_instances",
        ["tenant_id", "user_id", "updated_at"],
    )
    op.create_index(
        "ix_copilot_workflows_worker", "copilot_workflow_instances", ["status", "lease_until"]
    )
    op.create_table(
        "copilot_workflow_steps",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("workflow_id", sa.BigInteger(), nullable=False),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("step_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("safe_result_summary", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','WAITING','SUCCEEDED','FAILED','SKIPPED',"
            "'CANCELLED','UNKNOWN')",
            name="ck_copilot_workflow_step_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_id"],
            ["copilot_workflow_instances.tenant_id", "copilot_workflow_instances.id"],
            ondelete="CASCADE",
            name="fk_copilot_workflow_steps_workflow",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_workflow_steps_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "workflow_id", "step_key", name="uq_copilot_workflow_step_key"
        ),
    )
    op.create_index(
        "ix_copilot_workflow_steps_workflow",
        "copilot_workflow_steps",
        ["tenant_id", "workflow_id", "id"],
    )
    op.create_table(
        "copilot_workflow_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("workflow_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("event_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_id"],
            ["copilot_workflow_instances.tenant_id", "copilot_workflow_instances.id"],
            ondelete="CASCADE",
            name="fk_copilot_workflow_events_workflow",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copilot_workflow_events_workflow",
        "copilot_workflow_events",
        ["tenant_id", "workflow_id", "id"],
    )
    op.create_table(
        "copilot_workflow_step_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("step_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "step_id"],
            ["copilot_workflow_steps.tenant_id", "copilot_workflow_steps.id"],
            ondelete="CASCADE",
            name="fk_copilot_workflow_attempts_step",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "step_id", "attempt_no", name="uq_copilot_workflow_step_attempt"
        ),
    )


def downgrade() -> None:
    op.drop_table("copilot_workflow_step_attempts")
    op.drop_index("ix_copilot_workflow_events_workflow", table_name="copilot_workflow_events")
    op.drop_table("copilot_workflow_events")
    op.drop_index("ix_copilot_workflow_steps_workflow", table_name="copilot_workflow_steps")
    op.drop_table("copilot_workflow_steps")
    op.drop_index("ix_copilot_workflows_worker", table_name="copilot_workflow_instances")
    op.drop_index("ix_copilot_workflows_owner_updated", table_name="copilot_workflow_instances")
    op.drop_table("copilot_workflow_instances")
