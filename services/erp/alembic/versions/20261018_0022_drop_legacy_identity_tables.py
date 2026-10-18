"""删除 ERP 遗留身份表，改为展示名快照。

Revision ID: 20261018_0022
Revises: 20261018_0021
Create Date: 2026-10-18

升级前请先备份 users/tenants/tenant_members/roles/permissions/member_roles/role_permissions。
本迁移会先把 users.display_name 回填到 identity_name_snapshots，再 DROP 身份表。
测试库可直接 upgrade；本地有业务数据的 neorvion_erp 需人工执行。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "20261018_0022"
down_revision: str | None = "20261018_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTITY_TABLES = (
    "member_roles",
    "role_permissions",
    "roles",
    "permissions",
    "tenant_members",
    "tenants",
    "users",
)


def upgrade() -> None:
    """回填展示名快照后删除 IAM 已接管的身份表。业务表 user_id / tenant_id 列保留。"""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "identity_name_snapshots" not in tables:
        op.create_table(
            "identity_name_snapshots",
            sa.Column(
                "user_id",
                sa.BigInteger(),
                autoincrement=False,
                nullable=False,
                comment="IAM users.id",
            ),
            sa.Column("display_name", sa.String(length=64), nullable=False, comment="展示名快照"),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("user_id"),
        )

    if "users" in tables:
        bind.execute(
            text(
                """
                INSERT INTO identity_name_snapshots (user_id, display_name, updated_at)
                SELECT id, display_name, NOW()
                FROM users
                ON DUPLICATE KEY UPDATE
                    display_name = VALUES(display_name),
                    updated_at = VALUES(updated_at)
                """
            )
        )

    bind.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    try:
        for table in _IDENTITY_TABLES:
            if table not in tables:
                continue
            for fk in inspector.get_foreign_keys(table):
                name = fk.get("name")
                if name:
                    op.drop_constraint(name, table_name=table, type_="foreignkey")
        for table in _IDENTITY_TABLES:
            if table in tables:
                op.drop_table(table)
    finally:
        bind.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def downgrade() -> None:
    """不重建身份库。恢复请导入 mysqldump 备份。"""
    return
