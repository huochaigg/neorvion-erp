"""add action proposals, revisions and validations

Revision ID: 20261023_0003
Revises: 20261023_0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261023_0003"
down_revision = "20261023_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_action_proposals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger()),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('DRAFT','NEEDS_INPUT','READY','STALE','CANCELLED','EXPIRED')", name="ck_copilot_action_proposals_status"),
        sa.ForeignKeyConstraint(["tenant_id", "user_id", "conversation_id"], ["copilot_conversations.tenant_id", "copilot_conversations.user_id", "copilot_conversations.id"], ondelete="CASCADE", name="fk_copilot_action_proposals_conversation_owner"),
        sa.ForeignKeyConstraint(["tenant_id", "source_message_id"], ["copilot_messages.tenant_id", "copilot_messages.id"], name="fk_copilot_action_proposals_source_message"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_action_proposals_tenant_id"),
        sa.UniqueConstraint("tenant_id", "user_id", "id", name="uq_copilot_action_proposals_owner"),
        sa.UniqueConstraint("tenant_id", "user_id", "idempotency_key", name="uq_copilot_action_proposals_idempotency"),
    )
    op.create_index("ix_copilot_action_proposals_tenant_id", "copilot_action_proposals", ["tenant_id"])
    op.create_index("ix_copilot_action_proposals_owner_updated", "copilot_action_proposals", ["tenant_id", "user_id", "updated_at"])
    op.create_table(
        "copilot_proposal_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("proposal_id", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("editor_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id", "proposal_id"], ["copilot_action_proposals.tenant_id", "copilot_action_proposals.id"], ondelete="CASCADE", name="fk_copilot_proposal_revisions_proposal"),
        sa.UniqueConstraint("tenant_id", "proposal_id", "revision", name="uq_copilot_proposal_revision"),
    )
    op.create_index("ix_copilot_proposal_revisions_tenant_id", "copilot_proposal_revisions", ["tenant_id"])
    op.create_index("ix_copilot_proposal_revisions_proposal", "copilot_proposal_revisions", ["tenant_id", "proposal_id"])
    op.create_table(
        "copilot_proposal_validations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("proposal_id", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("errors", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("missing_fields", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("preview_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("resource_versions", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('VALID','INVALID','UNAVAILABLE')", name="ck_copilot_proposal_validations_status"),
        sa.ForeignKeyConstraint(["tenant_id", "proposal_id"], ["copilot_action_proposals.tenant_id", "copilot_action_proposals.id"], ondelete="CASCADE", name="fk_copilot_proposal_validations_proposal"),
        sa.UniqueConstraint("tenant_id", "proposal_id", "revision", name="uq_copilot_proposal_validation_revision"),
    )
    op.create_index("ix_copilot_proposal_validations_tenant_id", "copilot_proposal_validations", ["tenant_id"])
    op.create_index("ix_copilot_proposal_validations_proposal", "copilot_proposal_validations", ["tenant_id", "proposal_id"])


def downgrade() -> None:
    op.drop_table("copilot_proposal_validations")
    op.drop_table("copilot_proposal_revisions")
    op.drop_table("copilot_action_proposals")
