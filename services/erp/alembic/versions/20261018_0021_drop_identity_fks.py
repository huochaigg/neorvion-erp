"""去掉业务表对 users / tenants 的外键。身份数据归 IAM，ERP 只保留整数 ID 契约。

Revision ID: 20261018_0021
Revises: 20261013_0020
Create Date: 2026-10-18
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "20261018_0021"
down_revision: str | None = "20261013_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEEP_TABLES = {"users", "tenants", "tenant_members", "roles", "role_permissions", "member_roles", "permissions"}


def upgrade() -> None:
    """删除业务表指向 IAM 已迁出身份表的外键，保留列与整数语义。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in inspector.get_table_names():
        if table in _KEEP_TABLES:
            continue
        for fk in inspector.get_foreign_keys(table):
            referred = fk.get("referred_table")
            name = fk.get("name")
            if referred in {"users", "tenants"} and name:
                op.drop_constraint(name, table_name=table, type_="foreignkey")


def downgrade() -> None:
    """身份外键不再重建。恢复请使用迁移前的数据库备份。"""
    return
