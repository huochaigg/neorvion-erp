"""V1 Knowledge：写入知识库权限目录，并给历史系统角色补齐模板权限。

Revision ID: 20261013_0020
Revises: 20261012_0019
Create Date: 2026-10-13
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.orm import Session

revision: str = "20261013_0020"
down_revision: str | None = "20261012_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """幂等补齐 knowledge:* 目录，并按默认模板给系统角色只增不删。"""
    session = Session(bind=op.get_bind())
    from app.services.rbac import RoleService

    service = RoleService(session)
    service.seed_permission_catalog()
    service.backfill_existing_tenants()
    session.flush()


def downgrade() -> None:
    """不删除权限目录行，避免历史角色授权断裂。"""
    return
