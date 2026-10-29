"""V13 production hardening and monetary budget audit.

Revision ID: 20261029_0013
Revises: 20261028_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261029_0013"
down_revision: str | None = "20261028_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copilot_ai_budget_reservations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("reservation_id", sa.String(64), nullable=False),
        sa.Column("scenario", sa.String(24), nullable=False),
        sa.Column("period_key", sa.String(6), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("estimated_tokens", sa.BigInteger(), nullable=False),
        sa.Column("charged_tokens", sa.BigInteger(), nullable=True),
        sa.Column("estimated_money_micros", sa.BigInteger(), nullable=False),
        sa.Column("charged_money_micros", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("pricing_version", sa.String(64), nullable=False),
        sa.Column("usage_trusted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "reservation_id", name="uq_ai_budget_reservation"),
    )
    op.create_index(
        "ix_ai_budget_reservation_period",
        "copilot_ai_budget_reservations",
        ["tenant_id", "period_key", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_budget_reservation_period", table_name="copilot_ai_budget_reservations"
    )
    op.drop_table("copilot_ai_budget_reservations")
