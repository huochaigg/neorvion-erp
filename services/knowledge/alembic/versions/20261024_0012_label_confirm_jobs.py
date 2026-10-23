"""智能标注批量确认改为可恢复的后台任务。

Revision ID: 20261024_0012
Revises: 20261022_0011
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0012"
down_revision: str | None = "20261022_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_label_jobs",
        sa.Column("job_type", sa.String(16), nullable=False, server_default="SUGGEST"),
    )
    op.add_column(
        "evaluation_label_jobs",
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_label_jobs",
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "evaluation_label_jobs",
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.execute("UPDATE evaluation_label_jobs SET succeeded = drafted WHERE succeeded = 0")


def downgrade() -> None:
    op.drop_column("evaluation_label_jobs", "details")
    op.drop_column("evaluation_label_jobs", "succeeded")
    op.drop_column("evaluation_label_jobs", "processed")
    op.drop_column("evaluation_label_jobs", "job_type")
