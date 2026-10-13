"""V8 采购收货与销售出库。修正销售明细预占与已出库约束。

Revision ID: 20261006_0013
Revises: 20261005_0012
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006_0013"
down_revision: str | None = "20261005_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # V7 要求 shipped <= reserved。正式出库后 reserved 下降、shipped 上升，该约束会挡掉合法数据。
    # 不重建表，只替换 CHECK。已有数据 shipped=0，新约束仍然成立。
    op.drop_constraint(
        "ck_so_items_shipped_lte_reserved",
        "sales_order_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_so_items_reserved_lte_qty",
        "sales_order_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_so_items_reserved_plus_shipped",
        "sales_order_items",
        "reserved_quantity + shipped_quantity <= quantity",
    )

    op.create_table(
        "purchase_receipts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("receipt_no", sa.String(length=32), nullable=True),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("received_by", sa.BigInteger(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_purchase_receipts_tenant"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_purchase_receipts_creator"),
        sa.ForeignKeyConstraint(
            ["received_by"],
            ["users.id"],
            name="fk_purchase_receipts_receiver",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name="fk_purchase_receipts_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_purchase_receipts_warehouse",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_purchase_receipts_tenant_id"),
        sa.UniqueConstraint("tenant_id", "receipt_no", name="uq_purchase_receipts_tenant_no"),
    )
    op.create_index("ix_purchase_receipts_tenant_id", "purchase_receipts", ["tenant_id"])
    op.create_index(
        "ix_purchase_receipts_tenant_status",
        "purchase_receipts",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_purchase_receipts_tenant_order",
        "purchase_receipts",
        ["tenant_id", "purchase_order_id"],
    )
    op.create_index(
        "ix_purchase_receipts_tenant_created",
        "purchase_receipts",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "purchase_receipt_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_receipt_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("expected_quantity", sa.Integer(), nullable=False),
        sa.Column("received_quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_pr_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_receipt_id"],
            ["purchase_receipts.tenant_id", "purchase_receipts.id"],
            name="fk_pr_items_receipt",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_item_id"],
            ["purchase_order_items.tenant_id", "purchase_order_items.id"],
            name="fk_pr_items_po_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_pr_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pr_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "purchase_receipt_id",
            "purchase_order_item_id",
            name="uq_pr_items_receipt_po_item",
        ),
        sa.CheckConstraint("expected_quantity > 0", name="ck_pr_items_expected_positive"),
        sa.CheckConstraint("received_quantity > 0", name="ck_pr_items_received_positive"),
        sa.CheckConstraint(
            "received_quantity <= expected_quantity",
            name="ck_pr_items_received_lte_expected",
        ),
    )
    op.create_index("ix_pr_items_tenant_id", "purchase_receipt_items", ["tenant_id"])
    op.create_index(
        "ix_pr_items_tenant_receipt",
        "purchase_receipt_items",
        ["tenant_id", "purchase_receipt_id"],
    )

    op.create_table(
        "outbound_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("outbound_no", sa.String(length=32), nullable=True),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="PENDING_PICKING",
        ),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("picked_at", sa.DateTime(), nullable=True),
        sa.Column("picked_by", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_outbound_orders_tenant"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_outbound_orders_creator"),
        sa.ForeignKeyConstraint(
            ["picked_by"],
            ["users.id"],
            name="fk_outbound_orders_picker",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
            name="fk_outbound_orders_confirmer",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_outbound_orders_sales",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_outbound_orders_warehouse",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_outbound_orders_tenant_id"),
        sa.UniqueConstraint("tenant_id", "outbound_no", name="uq_outbound_orders_tenant_no"),
    )
    op.create_index("ix_outbound_orders_tenant_id", "outbound_orders", ["tenant_id"])
    op.create_index(
        "ix_outbound_orders_tenant_status",
        "outbound_orders",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_outbound_orders_tenant_sales",
        "outbound_orders",
        ["tenant_id", "sales_order_id"],
    )
    op.create_index(
        "ix_outbound_orders_tenant_created",
        "outbound_orders",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "outbound_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("outbound_order_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("planned_quantity", sa.Integer(), nullable=False),
        sa.Column("picked_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outbound_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_ob_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outbound_order_id"],
            ["outbound_orders.tenant_id", "outbound_orders.id"],
            name="fk_ob_items_outbound",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_item_id"],
            ["sales_order_items.tenant_id", "sales_order_items.id"],
            name="fk_ob_items_so_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_ob_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_ob_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "outbound_order_id",
            "sales_order_item_id",
            name="uq_ob_items_outbound_so_item",
        ),
        sa.CheckConstraint("planned_quantity > 0", name="ck_ob_items_planned_positive"),
        sa.CheckConstraint("picked_quantity >= 0", name="ck_ob_items_picked_nonneg"),
        sa.CheckConstraint("outbound_quantity >= 0", name="ck_ob_items_outbound_nonneg"),
        sa.CheckConstraint(
            "picked_quantity <= planned_quantity",
            name="ck_ob_items_picked_lte_planned",
        ),
        sa.CheckConstraint(
            "outbound_quantity <= picked_quantity",
            name="ck_ob_items_outbound_lte_picked",
        ),
    )
    op.create_index("ix_ob_items_tenant_id", "outbound_order_items", ["tenant_id"])
    op.create_index(
        "ix_ob_items_tenant_outbound",
        "outbound_order_items",
        ["tenant_id", "outbound_order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ob_items_tenant_outbound", table_name="outbound_order_items")
    op.drop_index("ix_ob_items_tenant_id", table_name="outbound_order_items")
    op.drop_table("outbound_order_items")
    op.drop_index("ix_outbound_orders_tenant_created", table_name="outbound_orders")
    op.drop_index("ix_outbound_orders_tenant_sales", table_name="outbound_orders")
    op.drop_index("ix_outbound_orders_tenant_status", table_name="outbound_orders")
    op.drop_index("ix_outbound_orders_tenant_id", table_name="outbound_orders")
    op.drop_table("outbound_orders")
    op.drop_index("ix_pr_items_tenant_receipt", table_name="purchase_receipt_items")
    op.drop_index("ix_pr_items_tenant_id", table_name="purchase_receipt_items")
    op.drop_table("purchase_receipt_items")
    op.drop_index("ix_purchase_receipts_tenant_created", table_name="purchase_receipts")
    op.drop_index("ix_purchase_receipts_tenant_order", table_name="purchase_receipts")
    op.drop_index("ix_purchase_receipts_tenant_status", table_name="purchase_receipts")
    op.drop_index("ix_purchase_receipts_tenant_id", table_name="purchase_receipts")
    op.drop_table("purchase_receipts")
    op.drop_constraint(
        "ck_so_items_reserved_plus_shipped",
        "sales_order_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_so_items_reserved_lte_qty",
        "sales_order_items",
        "reserved_quantity <= quantity",
    )
    op.create_check_constraint(
        "ck_so_items_shipped_lte_reserved",
        "sales_order_items",
        "shipped_quantity <= reserved_quantity",
    )
