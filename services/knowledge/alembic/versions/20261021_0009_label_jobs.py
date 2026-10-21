"""智能初标改为后台任务，HTTP 只返回已接受。

Revision ID: 20261021_0009
Revises: 20261021_0008
Create Date: 2026-10-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261021_0009"
down_revision: str | None = "20261021_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_label_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="QUEUED"),
        sa.Column("options", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drafted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_eval_label_jobs_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_label_jobs_dataset_tenant",
        ),
    )
    op.create_index("ix_evaluation_label_jobs_tenant_id", "evaluation_label_jobs", ["tenant_id"])
    op.create_index(
        "uq_eval_label_jobs_active",
        "evaluation_label_jobs",
        ["tenant_id", "dataset_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_eval_label_jobs_active", table_name="evaluation_label_jobs")
    op.drop_index("ix_evaluation_label_jobs_tenant_id", table_name="evaluation_label_jobs")
    op.drop_table("evaluation_label_jobs")
