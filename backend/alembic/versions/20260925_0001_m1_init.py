"""M1 初始化迁移链路。

Revision ID: 20260925_0001
Revises:
Create Date: 2026-09-25
"""

from collections.abc import Sequence

revision: str = "20260925_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """M1 只建立 Alembic 工作流，业务表从 M2 开始创建。"""


def downgrade() -> None:
    """无结构可回滚。"""
