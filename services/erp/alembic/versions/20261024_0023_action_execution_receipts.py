"""ERP Copilot V6 最终写入幂等凭据。

Revision ID: 20261024_0023
Revises: 20261018_0022
"""

import sqlalchemy as sa
from alembic import op

revision = "20261024_0023"
down_revision = "20261018_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_action_execution_receipts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("execution_key", sa.String(128), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("proposal_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("resource_type", sa.String(40)),
        sa.Column("resource_id", sa.BigInteger()),
        sa.Column("resource_no", sa.String(64)),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.CheckConstraint(
            "status IN ('EXECUTING','SUCCEEDED')", name="ck_erp_action_receipt_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "execution_key", name="uq_erp_action_receipt_key"),
    )
    op.create_index(
        "ix_erp_action_receipt_resource",
        "erp_action_execution_receipts",
        ["tenant_id", "resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_erp_action_receipt_resource", table_name="erp_action_execution_receipts")
    op.drop_table("erp_action_execution_receipts")
