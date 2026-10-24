"""V6 confirmations approvals executions audit and durable graph state.

Revision ID: 20261024_0004
Revises: 20261023_0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261024_0004"
down_revision = "20261023_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_action_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("proposal_id", sa.BigInteger(), nullable=False),
        sa.Column("proposal_revision", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("execution_key", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("client_request_id", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("confirmation_nonce_hash", sa.String(64), nullable=False),
        sa.Column("confirmation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("approval_id", sa.BigInteger()),
        sa.Column("erp_resource_type", sa.String(40)),
        sa.Column("erp_resource_id", sa.BigInteger()),
        sa.Column("erp_resource_no", sa.String(64)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            ["copilot_action_proposals.tenant_id", "copilot_action_proposals.id"],
            ondelete="RESTRICT",
            name="fk_action_execution_proposal",
        ),
        sa.UniqueConstraint(
            "tenant_id", "proposal_id", "proposal_revision", name="uq_action_execution_revision"
        ),
        sa.UniqueConstraint("tenant_id", "execution_key", name="uq_action_execution_key"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_action_execution_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "client_request_id", name="uq_action_execution_client_request"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_CONFIRMATION','WAITING_APPROVAL','APPROVED',"
            "'EXECUTING','SUCCEEDED','FAILED','UNKNOWN','RECONCILING',"
            "'REJECTED','CANCELLED','EXPIRED')",
            name="ck_action_execution_status",
        ),
    )
    op.create_index(
        "ix_action_execution_owner_created",
        "copilot_action_executions",
        ["tenant_id", "user_id", "created_at"],
    )
    op.create_index(
        "ix_copilot_action_executions_tenant_id", "copilot_action_executions", ["tenant_id"]
    )
    op.create_table(
        "copilot_action_approvals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("proposal_id", sa.BigInteger(), nullable=False),
        sa.Column("proposal_revision", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=False),
        sa.Column("applicant_user_id", sa.BigInteger(), nullable=False),
        sa.Column("approver_user_id", sa.BigInteger()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decision", sa.String(16)),
        sa.Column("decision_reason", sa.String(500)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["copilot_action_executions.tenant_id", "copilot_action_executions.id"],
            ondelete="RESTRICT",
            name="fk_action_approval_execution",
        ),
        sa.UniqueConstraint("tenant_id", "execution_id", name="uq_action_approval_execution"),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','EXPIRED','REVOKED')",
            name="ck_action_approval_status",
        ),
    )
    op.create_index(
        "ix_action_approval_queue",
        "copilot_action_approvals",
        ["tenant_id", "status", "requested_at"],
    )
    op.create_index(
        "ix_copilot_action_approvals_tenant_id", "copilot_action_approvals", ["tenant_id"]
    )
    op.create_table(
        "copilot_action_execution_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("erp_request_id", sa.String(128)),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "execution_id"],
            ["copilot_action_executions.tenant_id", "copilot_action_executions.id"],
            ondelete="CASCADE",
            name="fk_action_attempt_execution",
        ),
        sa.UniqueConstraint("tenant_id", "execution_id", "attempt_no", name="uq_action_attempt_no"),
    )
    op.create_index(
        "ix_copilot_action_execution_attempts_tenant_id",
        "copilot_action_execution_attempts",
        ["tenant_id"],
    )
    op.create_table(
        "copilot_action_audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_user_id", sa.BigInteger()),
        sa.Column("proposal_id", sa.BigInteger(), nullable=False),
        sa.Column("execution_id", sa.BigInteger()),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("details", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_audit_execution",
        "copilot_action_audit_events",
        ["tenant_id", "execution_id", "created_at"],
    )
    op.create_index(
        "ix_copilot_action_audit_events_tenant_id", "copilot_action_audit_events", ["tenant_id"]
    )
    op.create_table(
        "copilot_action_graph_checkpoints",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("node", sa.String(40), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "execution_id", name="uq_action_graph_checkpoint"),
        sa.UniqueConstraint("thread_id", name="uq_action_graph_thread_id"),
    )
    op.create_index(
        "ix_copilot_action_graph_checkpoints_tenant_id",
        "copilot_action_graph_checkpoints",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_table("copilot_action_graph_checkpoints")
    op.drop_table("copilot_action_audit_events")
    op.drop_table("copilot_action_execution_attempts")
    op.drop_table("copilot_action_approvals")
    op.drop_table("copilot_action_executions")
