"""V2.3.5 企业内成员名称与细粒度权限。

Revision ID: 20260928_0006
Revises: 20260928_0005
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision: str = "20260928_0006"
down_revision: str | None = "20260928_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_members",
        sa.Column("display_name", sa.String(length=64), nullable=True),
    )
    # 与迁移共用连接，只 flush。seed 幂等，旧 manage 会展开成细粒度权限，不删旧 code。
    session = Session(bind=op.get_bind())
    from app.services.rbac import RoleService

    service = RoleService(session)
    service.seed_permission_catalog()
    service.expand_legacy_manage_permissions()
    session.flush()


def downgrade() -> None:
    op.drop_column("tenant_members", "display_name")
