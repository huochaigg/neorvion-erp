"""V1 Knowledge：写入知识库权限目录，并给历史系统角色补齐模板权限。

Revision ID: 20261013_0020
Revises: 20261012_0019
Create Date: 2026-10-13
"""

from collections.abc import Sequence

revision: str = "20261013_0020"
down_revision: str | None = "20261012_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """knowledge:* 权限目录改由 IAM seed_permissions 维护，ERP 不再写权限表。"""
    return


def downgrade() -> None:
    """不删除权限目录行，避免历史角色授权断裂。"""
    return
