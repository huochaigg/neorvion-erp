"""V15 intent context store and INTENT_LIVE evaluation kind.

Revision ID: 20261123_0017
Revises: 20261120_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261123_0017"
down_revision: str | None = "20261120_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copilot_intent_contexts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="IDLE", nullable=False),
        sa.Column("intent_key", sa.String(length=64)),
        sa.Column("collected_slots", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("missing_slots", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("entities", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("last_resolution", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("message_summaries", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("last_request_id", sa.String(length=64), server_default="", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('IDLE','COLLECTING','READY','CANCELLED','EXPIRED')",
            name="ck_copilot_intent_context_status",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_copilot_intent_contexts_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "conversation_id",
            name="uq_copilot_intent_contexts_owner_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id", "conversation_id"],
            [
                "copilot_conversations.tenant_id",
                "copilot_conversations.user_id",
                "copilot_conversations.id",
            ],
            ondelete="CASCADE",
            name="fk_copilot_intent_context_conversation_owner",
        ),
    )
    op.create_index(
        "ix_copilot_intent_contexts_expiry",
        "copilot_intent_contexts",
        ["status", "expires_at"],
    )
    op.drop_constraint(
        "ck_agent_eval_execution_kind",
        "copilot_agent_evaluation_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_eval_execution_kind",
        "copilot_agent_evaluation_runs",
        "execution_kind IN ('REPLAY','LIVE','SELECTOR_LIVE','INTENT_LIVE','END_TO_END')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE copilot_agent_evaluation_runs "
        "SET execution_kind = 'REPLAY' "
        "WHERE execution_kind = 'INTENT_LIVE'"
    )
    op.drop_constraint(
        "ck_agent_eval_execution_kind",
        "copilot_agent_evaluation_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_eval_execution_kind",
        "copilot_agent_evaluation_runs",
        "execution_kind IN ('REPLAY','LIVE','SELECTOR_LIVE','END_TO_END')",
    )
    op.drop_index("ix_copilot_intent_contexts_expiry", table_name="copilot_intent_contexts")
    op.drop_table("copilot_intent_contexts")
