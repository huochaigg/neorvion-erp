"""V10 库存盘点与调拨。流水类型加长以容纳 STOCKTAKE_ADJUSTMENT。

Revision ID: 20261010_0016
Revises: 20261008_0015
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261010_0016"
down_revision: str | None = "20261008_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # STOCKTAKE_ADJUSTMENT 超过原来的 16 位。TRANSFER_OUT / TRANSFER_IN 仍可放入 16，一并加长。
    op.alter_column(
        "inventory_transactions",
        "type",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )

    op.create_table(
        "stocktake_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("stocktake_no", sa.String(length=32), nullable=True),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="COUNTING", nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_stocktake_orders_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_stocktake_orders_warehouse",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_stocktake_orders_created_by"),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
            name="fk_stocktake_orders_confirmed_by",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"],
            ["users.id"],
            name="fk_stocktake_orders_cancelled_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_stocktake_orders_tenant_id"),
        sa.UniqueConstraint("tenant_id", "stocktake_no", name="uq_stocktake_orders_tenant_no"),
    )
    op.create_index("ix_stocktake_orders_tenant_id", "stocktake_orders", ["tenant_id"])
    op.create_index(
        "ix_stocktake_orders_tenant_status",
        "stocktake_orders",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_stocktake_orders_tenant_warehouse",
        "stocktake_orders",
        ["tenant_id", "warehouse_id"],
    )
    op.create_index(
        "ix_stocktake_orders_tenant_created",
        "stocktake_orders",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "stocktake_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("stocktake_order_id", sa.BigInteger(), nullable=False),
        sa.Column("inventory_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("system_quantity", sa.Integer(), nullable=False),
        sa.Column("system_reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("counted_quantity", sa.Integer(), nullable=True),
        sa.Column("difference_quantity", sa.Integer(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("system_quantity >= 0", name="ck_stocktake_items_system_nonneg"),
        sa.CheckConstraint(
            "system_reserved_quantity >= 0",
            name="ck_stocktake_items_reserved_nonneg",
        ),
        sa.CheckConstraint(
            "counted_quantity IS NULL OR counted_quantity >= 0",
            name="ck_stocktake_items_counted_nonneg",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_stocktake_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "stocktake_order_id"],
            ["stocktake_orders.tenant_id", "stocktake_orders.id"],
            name="fk_stocktake_items_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inventory_id"],
            ["inventories.tenant_id", "inventories.id"],
            name="fk_stocktake_items_inventory",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_stocktake_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_stocktake_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "stocktake_order_id",
            "inventory_id",
            name="uq_stocktake_items_order_inventory",
        ),
    )
    op.create_index("ix_stocktake_items_tenant_id", "stocktake_items", ["tenant_id"])
    op.create_index(
        "ix_stocktake_items_tenant_order",
        "stocktake_items",
        ["tenant_id", "stocktake_order_id"],
    )

    op.create_table(
        "stock_transfers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("transfer_no", sa.String(length=32), nullable=True),
        sa.Column("source_warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("target_warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("outbound_at", sa.DateTime(), nullable=True),
        sa.Column("outbound_by", sa.BigInteger(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("received_by", sa.BigInteger(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "source_warehouse_id <> target_warehouse_id",
            name="ck_stock_transfers_distinct_warehouses",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_stock_transfers_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_stock_transfers_source",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "target_warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_stock_transfers_target",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_stock_transfers_created_by"),
        sa.ForeignKeyConstraint(
            ["outbound_by"],
            ["users.id"],
            name="fk_stock_transfers_outbound_by",
        ),
        sa.ForeignKeyConstraint(
            ["received_by"],
            ["users.id"],
            name="fk_stock_transfers_received_by",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"],
            ["users.id"],
            name="fk_stock_transfers_cancelled_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_stock_transfers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "transfer_no", name="uq_stock_transfers_tenant_no"),
    )
    op.create_index("ix_stock_transfers_tenant_id", "stock_transfers", ["tenant_id"])
    op.create_index(
        "ix_stock_transfers_tenant_status",
        "stock_transfers",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_stock_transfers_tenant_source",
        "stock_transfers",
        ["tenant_id", "source_warehouse_id"],
    )
    op.create_index(
        "ix_stock_transfers_tenant_target",
        "stock_transfers",
        ["tenant_id", "target_warehouse_id"],
    )
    op.create_index(
        "ix_stock_transfers_tenant_created",
        "stock_transfers",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "stock_transfer_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("stock_transfer_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("outbound_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("received_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_st_items_qty_positive"),
        sa.CheckConstraint("outbound_quantity >= 0", name="ck_st_items_outbound_nonneg"),
        sa.CheckConstraint("received_quantity >= 0", name="ck_st_items_received_nonneg"),
        sa.CheckConstraint(
            "outbound_quantity <= quantity",
            name="ck_st_items_outbound_lte_qty",
        ),
        sa.CheckConstraint(
            "received_quantity <= outbound_quantity",
            name="ck_st_items_received_lte_outbound",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_st_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "stock_transfer_id"],
            ["stock_transfers.tenant_id", "stock_transfers.id"],
            name="fk_st_items_transfer",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_st_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_st_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "stock_transfer_id",
            "sku_id",
            name="uq_st_items_transfer_sku",
        ),
    )
    op.create_index("ix_st_items_tenant_id", "stock_transfer_items", ["tenant_id"])
    op.create_index(
        "ix_st_items_tenant_transfer",
        "stock_transfer_items",
        ["tenant_id", "stock_transfer_id"],
    )


def downgrade() -> None:
    op.drop_table("stock_transfer_items")
    op.drop_table("stock_transfers")
    op.drop_table("stocktake_items")
    op.drop_table("stocktake_orders")
    op.alter_column(
        "inventory_transactions",
        "type",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
