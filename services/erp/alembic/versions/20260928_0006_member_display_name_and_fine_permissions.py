"""V2.3.5 企业内成员名称与细粒度权限。

Revision ID: 20260928_0006
Revises: 20260928_0005
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_0006"
down_revision: str | None = "20260928_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_members",
        sa.Column("display_name", sa.String(length=64), nullable=True),
    )
    # 细粒度权限 seed 已迁到 IAM。本修订只加企业内展示名列。


def downgrade() -> None:
    op.drop_column("tenant_members", "display_name")
