"""V11 service identities.

Revision ID: 20261027_0003
Revises: 20261018_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_0003"
down_revision: str | None = "20261018_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_identities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("subject_type", sa.String(length=16), server_default="SERVICE", nullable=False),
        sa.Column("tenant_ids", sa.JSON(), nullable=False),
        sa.Column("allowed_audiences", sa.JSON(), nullable=False),
        sa.Column("allowed_scopes", sa.JSON(), nullable=False),
        sa.Column("allowed_resources", sa.JSON(), nullable=False),
        sa.Column("secret_hash", sa.String(length=255), nullable=False),
        sa.Column("credential_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_service_identities_public_id", "service_identities", ["public_id"], unique=True)
    op.create_table(
        "service_identity_audits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("service_identity_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("token_id_hash", sa.String(length=64), server_default="", nullable=False),
        sa.Column("safe_detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_identity_id"], ["service_identities.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_service_identity_audits_identity",
        "service_identity_audits",
        ["service_identity_id"],
    )
    op.create_index(
        "ix_service_identity_audits_event", "service_identity_audits", ["event_type"]
    )


def downgrade() -> None:
    op.drop_table("service_identity_audits")
    op.drop_table("service_identities")
