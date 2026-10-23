"""add copilot evidence records

Revision ID: 20261023_0002
Revises: 20261022_0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261023_0002"
down_revision = "20261022_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_evidences",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tool_call_id", sa.String(128), nullable=False),
        sa.Column("citation_id", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128)),
        sa.Column("knowledge_base_id", sa.BigInteger()),
        sa.Column("document_id", sa.BigInteger()),
        sa.Column("chunk_id", sa.BigInteger()),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("excerpt", sa.Text()),
        sa.Column("source_version", sa.Integer()),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("source_type IN ('ERP', 'KNOWLEDGE')", name="ck_copilot_evidences_source"),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["copilot_conversations.tenant_id", "copilot_conversations.id"], ondelete="CASCADE", name="fk_copilot_evidences_conversation_tenant"),
        sa.ForeignKeyConstraint(["tenant_id", "message_id"], ["copilot_messages.tenant_id", "copilot_messages.id"], ondelete="CASCADE", name="fk_copilot_evidences_message_tenant"),
        sa.UniqueConstraint("tenant_id", "message_id", "citation_id", name="uq_copilot_evidence_citation"),
    )
    op.create_index("ix_copilot_evidences_tenant_id", "copilot_evidences", ["tenant_id"])
    op.create_index("ix_copilot_evidences_message", "copilot_evidences", ["tenant_id", "message_id"])


def downgrade() -> None:
    op.drop_table("copilot_evidences")
