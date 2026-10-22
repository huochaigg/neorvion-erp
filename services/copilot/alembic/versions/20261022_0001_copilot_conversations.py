"""create copilot conversations, messages and tool runs

Revision ID: 20261022_0001
Revises:
"""
# ruff: noqa: E501
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261022_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_conversations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(128), server_default="New conversation", nullable=False),
        sa.Column("status", sa.String(16), server_default="ACTIVE", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('ACTIVE', 'DELETED')", name="ck_copilot_conversations_status"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_conversations_tenant_id"),
        sa.UniqueConstraint("tenant_id", "user_id", "id", name="uq_copilot_conversations_owner"),
    )
    op.create_index("ix_copilot_conversations_tenant_id", "copilot_conversations", ["tenant_id"])
    op.create_index("ix_copilot_conversations_owner_updated", "copilot_conversations", ["tenant_id", "user_id", "updated_at"])
    op.create_table(
        "copilot_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("client_request_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), server_default="", nullable=False),
        sa.Column("protocol_data", postgresql.JSONB()),
        sa.Column("error_code", sa.Integer()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            ["copilot_conversations.tenant_id", "copilot_conversations.user_id", "copilot_conversations.id"],
            ondelete="CASCADE",
            name="fk_copilot_messages_conversation_owner",
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_copilot_messages_role"),
        sa.CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')", name="ck_copilot_messages_status"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_messages_tenant_id"),
        sa.UniqueConstraint("tenant_id", "conversation_id", "client_request_id", "role", name="uq_copilot_messages_idempotency"),
    )
    op.create_index("ix_copilot_messages_tenant_id", "copilot_messages", ["tenant_id"])
    op.create_index("ix_copilot_messages_conversation_created", "copilot_messages", ["tenant_id", "conversation_id", "created_at"])
    op.create_index("ix_copilot_messages_running", "copilot_messages", ["tenant_id", "conversation_id", "status"])
    op.create_table(
        "copilot_tool_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("tool_call_id", sa.String(128), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="RUNNING", nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("input_summary", sa.Text()),
        sa.Column("output_summary", sa.Text()),
        sa.Column("error_code", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')", name="ck_copilot_tool_runs_status"),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["copilot_conversations.tenant_id", "copilot_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "message_id"], ["copilot_messages.tenant_id", "copilot_messages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_tool_runs_tenant_id"),
        sa.UniqueConstraint("tenant_id", "message_id", "tool_call_id", name="uq_copilot_tool_call"),
    )
    op.create_index("ix_copilot_tool_runs_tenant_id", "copilot_tool_runs", ["tenant_id"])
    op.create_index("ix_copilot_tool_runs_message", "copilot_tool_runs", ["tenant_id", "message_id"])


def downgrade() -> None:
    op.drop_table("copilot_tool_runs")
    op.drop_table("copilot_messages")
    op.drop_table("copilot_conversations")
