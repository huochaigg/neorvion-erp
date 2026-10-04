"""V5 库存台账与流水。维度是 Tenant + Warehouse + SKU。

Revision ID: 20261004_0010
Revises: 20261003_0009
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261004_0010"
down_revision: str | None = "20261003_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_inventories_quantity_nonneg"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_inventories_reserved_nonneg"),
        sa.CheckConstraint(
            "reserved_quantity <= quantity",
            name="ck_inventories_reserved_lte_qty",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_inventories_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_inventories_warehouse",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_inventories_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_inventories_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "warehouse_id",
            "sku_id",
            name="uq_inventories_tenant_warehouse_sku",
        ),
    )
    op.create_index("ix_inventories_tenant_id", "inventories", ["tenant_id"])
    op.create_index(
        "ix_inventories_tenant_warehouse",
        "inventories",
        ["tenant_id", "warehouse_id"],
    )
    op.create_index("ix_inventories_tenant_sku", "inventories", ["tenant_id", "sku_id"])

    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("inventory_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("change_quantity", sa.Integer(), nullable=False),
        sa.Column("before_quantity", sa.Integer(), nullable=False),
        sa.Column("after_quantity", sa.Integer(), nullable=False),
        sa.Column("before_reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("after_reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(length=32), nullable=True),
        sa.Column("reference_id", sa.BigInteger(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("operator_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_inventory_tx_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inventory_id"],
            ["inventories.tenant_id", "inventories.id"],
            name="fk_inventory_tx_inventory",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_inventory_tx_warehouse",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_inventory_tx_sku",
        ),
        sa.ForeignKeyConstraint(
            ["operator_user_id"],
            ["users.id"],
            name="fk_inventory_tx_operator",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_tx_tenant_id", "inventory_transactions", ["tenant_id"])
    op.create_index(
        "ix_inventory_tx_tenant_created",
        "inventory_transactions",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_inventory_tx_tenant_warehouse",
        "inventory_transactions",
        ["tenant_id", "warehouse_id"],
    )
    op.create_index(
        "ix_inventory_tx_tenant_sku",
        "inventory_transactions",
        ["tenant_id", "sku_id"],
    )
    op.create_index(
        "ix_inventory_tx_tenant_type",
        "inventory_transactions",
        ["tenant_id", "type"],
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_tx_tenant_type", table_name="inventory_transactions")
    op.drop_index("ix_inventory_tx_tenant_sku", table_name="inventory_transactions")
    op.drop_index("ix_inventory_tx_tenant_warehouse", table_name="inventory_transactions")
    op.drop_index("ix_inventory_tx_tenant_created", table_name="inventory_transactions")
    op.drop_index("ix_inventory_tx_tenant_id", table_name="inventory_transactions")
    op.drop_table("inventory_transactions")
    op.drop_index("ix_inventories_tenant_sku", table_name="inventories")
    op.drop_index("ix_inventories_tenant_warehouse", table_name="inventories")
    op.drop_index("ix_inventories_tenant_id", table_name="inventories")
    op.drop_table("inventories")
