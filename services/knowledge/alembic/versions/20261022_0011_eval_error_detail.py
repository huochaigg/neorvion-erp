"""评测运行保存脱敏后的中断诊断。

Revision ID: 20261022_0011
Revises: 20261022_0010
Create Date: 2026-10-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261022_0011"
down_revision: str | None = "20261022_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("error_detail", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "error_detail")
