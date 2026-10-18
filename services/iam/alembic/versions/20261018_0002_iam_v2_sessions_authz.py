"""IAM V2：登录会话、授权版本、权限归属与角色状态。

Revision ID: 20261018_0002
Revises: 20261018_0001
Create Date: 2026-10-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261018_0002"
down_revision: str | None = "20261018_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "permissions",
        sa.Column("application_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "permissions",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
    )
    op.create_index("ix_permissions_application_id", "permissions", ["application_id"])
    op.create_foreign_key(
        "fk_permissions_application",
        "permissions",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "roles",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.String(length=32), nullable=False),
        sa.Column("refresh_jti_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_jti_hash", sa.String(length=64), nullable=True),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("ip_address", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoke_reason", sa.String(length=32), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_sessions_user", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_auth_sessions_public_id"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])
    op.create_index("ix_auth_sessions_refresh_jti_hash", "auth_sessions", ["refresh_jti_hash"])

    op.create_table(
        "authz_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_authz_revisions_user_tenant"),
    )
    op.create_index("ix_authz_revisions_user_id", "authz_revisions", ["user_id"])
    op.create_index("ix_authz_revisions_tenant_id", "authz_revisions", ["tenant_id"])

    op.create_table(
        "authz_outbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_authz_outbox_user_id", "authz_outbox", ["user_id"])
    op.create_index("ix_authz_outbox_tenant_id", "authz_outbox", ["tenant_id"])
    op.create_index("ix_authz_outbox_processed_at", "authz_outbox", ["processed_at"])

    op.execute(
        """
        UPDATE permissions p
        INNER JOIN applications a ON a.code = CASE
            WHEN p.module IN ('iam', 'tenant') THEN 'iam'
            WHEN p.module = 'knowledge' THEN 'knowledge'
            ELSE 'erp'
        END
        SET p.application_id = a.id
        WHERE p.application_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_table("authz_outbox")
    op.drop_table("authz_revisions")
    op.drop_table("auth_sessions")
    op.drop_constraint("fk_permissions_application", "permissions", type_="foreignkey")
    op.drop_index("ix_permissions_application_id", table_name="permissions")
    op.drop_column("permissions", "status")
    op.drop_column("permissions", "application_id")
    op.drop_column("roles", "status")
