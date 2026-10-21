"""评测智能初标草稿。确认前不进入正式 Ground Truth。

Revision ID: 20261021_0008
Revises: 20261019_0007
Create Date: 2026-10-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261021_0008"
down_revision: str | None = "20261019_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_label_suggestions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="LOW"),
        sa.Column("verdict", sa.String(32), nullable=False, server_default="INSUFFICIENT"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk", sa.Text(), nullable=False, server_default=""),
        sa.Column("items", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "original_items",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_eval_label_suggestions_tenant_id"),
        sa.UniqueConstraint("tenant_id", "case_id", name="uq_eval_label_suggestions_case"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["evaluation_cases.tenant_id", "evaluation_cases.id"],
            name="fk_eval_label_suggestions_case_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_label_suggestions_dataset_tenant",
        ),
    )
    op.create_index(
        "ix_eval_label_suggestions_dataset",
        "evaluation_label_suggestions",
        ["tenant_id", "dataset_id", "status"],
    )
    op.create_index(
        "ix_evaluation_label_suggestions_tenant_id",
        "evaluation_label_suggestions",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_label_suggestions_tenant_id", table_name="evaluation_label_suggestions")
    op.drop_index("ix_eval_label_suggestions_dataset", table_name="evaluation_label_suggestions")
    op.drop_table("evaluation_label_suggestions")
