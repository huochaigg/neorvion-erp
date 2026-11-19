"""V14.2 hybrid selection, pending inputs and auditable skill plans.

Revision ID: 20261119_0015
Revises: 20261113_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261119_0015"
down_revision: str | None = "20261113_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_skill_run_tenant", "copilot_skill_runs", ["tenant_id", "id"])
    op.add_column("copilot_skill_runs", sa.Column("selection_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("copilot_skill_runs", sa.Column("plan_id", sa.BigInteger(), nullable=True))
    op.add_column("copilot_skill_runs", sa.Column("plan_step_key", sa.String(64), nullable=True))

    op.create_table(
        "copilot_pending_skill_invocations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_version_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), server_default="COLLECTING_INPUT", nullable=False),
        sa.Column("collected_input", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("missing_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("selection_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("plan_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("clarification", sa.String(500), nullable=False),
        sa.Column("last_client_request_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('COLLECTING_INPUT','READY','CANCELLED','EXPIRED')", name="ck_pending_skill_status"),
        sa.ForeignKeyConstraint(["tenant_id", "user_id", "conversation_id"], ["copilot_conversations.tenant_id", "copilot_conversations.user_id", "copilot_conversations.id"], ondelete="CASCADE", name="fk_pending_skill_conversation_owner"),
        sa.ForeignKeyConstraint(["tenant_id", "skill_version_id"], ["copilot_skill_versions.tenant_id", "copilot_skill_versions.id"], ondelete="RESTRICT", name="fk_pending_skill_version"),
    )
    op.create_index("uq_pending_skill_active_conversation", "copilot_pending_skill_invocations", ["tenant_id", "user_id", "conversation_id"], unique=True, postgresql_where=sa.text("status = 'COLLECTING_INPUT'"))
    op.create_index("ix_pending_skill_expiry", "copilot_pending_skill_invocations", ["status", "expires_at"])

    op.create_table(
        "copilot_skill_execution_plans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("status", sa.String(24), server_default="CREATED", nullable=False),
        sa.Column("classification", postgresql.JSONB(), nullable=False),
        sa.Column("selection_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("budget_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("safe_error", sa.String(255)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('CREATED','RUNNING','SUCCEEDED','PARTIAL_FAILED','FAILED','CANCELLED','EXPIRED')", name="ck_skill_plan_status"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_skill_plan_tenant"),
        sa.UniqueConstraint("tenant_id", "user_id", "idempotency_key", name="uq_skill_plan_key"),
        sa.ForeignKeyConstraint(["tenant_id", "user_id", "conversation_id"], ["copilot_conversations.tenant_id", "copilot_conversations.user_id", "copilot_conversations.id"], ondelete="CASCADE", name="fk_skill_plan_conversation_owner"),
        sa.ForeignKeyConstraint(["tenant_id", "message_id"], ["copilot_messages.tenant_id", "copilot_messages.id"], ondelete="RESTRICT", name="fk_skill_plan_message"),
    )
    op.create_index("ix_skill_plan_message", "copilot_skill_execution_plans", ["tenant_id", "message_id"])

    op.create_table(
        "copilot_skill_execution_plan_steps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_version_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("depends_on", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(24), server_default="PENDING", nullable=False),
        sa.Column("safe_error", sa.String(255)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','SKIPPED','CANCELLED')", name="ck_skill_plan_step_status"),
        sa.UniqueConstraint("tenant_id", "plan_id", "step_key", name="uq_skill_plan_step_key"),
        sa.ForeignKeyConstraint(["tenant_id", "plan_id"], ["copilot_skill_execution_plans.tenant_id", "copilot_skill_execution_plans.id"], ondelete="CASCADE", name="fk_skill_plan_step_plan"),
        sa.ForeignKeyConstraint(["tenant_id", "skill_version_id"], ["copilot_skill_versions.tenant_id", "copilot_skill_versions.id"], ondelete="RESTRICT", name="fk_skill_plan_step_version"),
    )
    op.create_index("ix_skill_plan_step_status", "copilot_skill_execution_plan_steps", ["tenant_id", "plan_id", "status"])
    op.create_foreign_key("fk_skill_run_plan", "copilot_skill_runs", "copilot_skill_execution_plans", ["tenant_id", "plan_id"], ["tenant_id", "id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_skill_run_plan", "copilot_skill_runs", type_="foreignkey")
    op.drop_table("copilot_skill_execution_plan_steps")
    op.drop_table("copilot_skill_execution_plans")
    op.drop_table("copilot_pending_skill_invocations")
    op.drop_column("copilot_skill_runs", "plan_step_key")
    op.drop_column("copilot_skill_runs", "plan_id")
    op.drop_column("copilot_skill_runs", "selection_snapshot")
    op.drop_constraint("uq_skill_run_tenant", "copilot_skill_runs", type_="unique")
