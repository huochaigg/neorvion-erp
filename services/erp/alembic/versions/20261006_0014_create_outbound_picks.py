"""拣货记录。每次拣货追加一行，不覆盖累计数量。

Revision ID: 20261006_0014
Revises: 20261006_0013
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_0014"
down_revision: str | None = "20261006_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbound_picks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("outbound_order_id", sa.BigInteger(), nullable=False),
        sa.Column("picked_at", sa.DateTime(), nullable=False),
        sa.Column("picked_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_outbound_picks_tenant"),
        sa.ForeignKeyConstraint(["picked_by"], ["users.id"], name="fk_outbound_picks_user"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outbound_order_id"],
            ["outbound_orders.tenant_id", "outbound_orders.id"],
            name="fk_outbound_picks_outbound",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_outbound_picks_tenant_id"),
    )
    op.create_index("ix_outbound_picks_tenant_id", "outbound_picks", ["tenant_id"])
    op.create_index(
        "ix_outbound_picks_tenant_outbound",
        "outbound_picks",
        ["tenant_id", "outbound_order_id"],
    )
    op.create_index(
        "ix_outbound_picks_tenant_picked_at",
        "outbound_picks",
        ["tenant_id", "picked_at"],
    )
    op.create_table(
        "outbound_pick_lines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("pick_id", sa.BigInteger(), nullable=False),
        sa.Column("outbound_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("picked_before", sa.Integer(), nullable=False),
        sa.Column("picked_after", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_ob_pick_lines_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "pick_id"],
            ["outbound_picks.tenant_id", "outbound_picks.id"],
            name="fk_ob_pick_lines_pick",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outbound_order_item_id"],
            ["outbound_order_items.tenant_id", "outbound_order_items.id"],
            name="fk_ob_pick_lines_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_ob_pick_lines_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ob_pick_lines_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "pick_id",
            "outbound_order_item_id",
            name="uq_ob_pick_lines_pick_item",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_ob_pick_lines_qty_positive"),
        sa.CheckConstraint("picked_before >= 0", name="ck_ob_pick_lines_before_nonneg"),
        sa.CheckConstraint(
            "picked_after = picked_before + quantity",
            name="ck_ob_pick_lines_after_sum",
        ),
    )
    op.create_index("ix_ob_pick_lines_tenant_id", "outbound_pick_lines", ["tenant_id"])
    op.create_index(
        "ix_ob_pick_lines_tenant_pick",
        "outbound_pick_lines",
        ["tenant_id", "pick_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ob_pick_lines_tenant_pick", table_name="outbound_pick_lines")
    op.drop_index("ix_ob_pick_lines_tenant_id", table_name="outbound_pick_lines")
    op.drop_table("outbound_pick_lines")
    op.drop_index("ix_outbound_picks_tenant_picked_at", table_name="outbound_picks")
    op.drop_index("ix_outbound_picks_tenant_outbound", table_name="outbound_picks")
    op.drop_index("ix_outbound_picks_tenant_id", table_name="outbound_picks")
    op.drop_table("outbound_picks")
