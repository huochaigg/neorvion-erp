"""V6 供应商与采购单。采购审核不改库存。

Revision ID: 20261005_0011
Revises: 20261004_0010
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_0011"
down_revision: str | None = "20261004_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("contact_name", sa.String(length=64), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("contact_email", sa.String(length=128), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("province", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_suppliers_tenant"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_suppliers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
    )
    op.create_index("ix_suppliers_tenant_id", "suppliers", ["tenant_id"])
    op.create_index("ix_suppliers_tenant_status", "suppliers", ["tenant_id", "status"])

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("order_no", sa.String(length=32), nullable=True),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
        sa.Column("expected_arrival_date", sa.Date(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_by", sa.BigInteger(), nullable=True),
        sa.Column("reject_reason", sa.String(length=255), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.BigInteger(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_purchase_orders_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            name="fk_purchase_orders_supplier",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_purchase_orders_warehouse",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_purchase_orders_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_purchase_orders_approved_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rejected_by"],
            ["users.id"],
            name="fk_purchase_orders_rejected_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"],
            ["users.id"],
            name="fk_purchase_orders_cancelled_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_purchase_orders_tenant_id"),
        sa.UniqueConstraint("tenant_id", "order_no", name="uq_purchase_orders_tenant_order_no"),
    )
    op.create_index("ix_purchase_orders_tenant_id", "purchase_orders", ["tenant_id"])
    op.create_index(
        "ix_purchase_orders_tenant_status",
        "purchase_orders",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_purchase_orders_tenant_supplier",
        "purchase_orders",
        ["tenant_id", "supplier_id"],
    )
    op.create_index(
        "ix_purchase_orders_tenant_warehouse",
        "purchase_orders",
        ["tenant_id", "warehouse_id"],
    )
    op.create_index(
        "ix_purchase_orders_tenant_created",
        "purchase_orders",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "purchase_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_order_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("received_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_po_items_quantity_positive"),
        sa.CheckConstraint("received_quantity >= 0", name="ck_po_items_received_nonneg"),
        sa.CheckConstraint(
            "received_quantity <= quantity",
            name="ck_po_items_received_lte_qty",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_po_items_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name="fk_po_items_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_po_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_purchase_order_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "purchase_order_id",
            "sku_id",
            name="uq_po_items_tenant_order_sku",
        ),
    )
    op.create_index("ix_po_items_tenant_id", "purchase_order_items", ["tenant_id"])
    op.create_index(
        "ix_po_items_tenant_order",
        "purchase_order_items",
        ["tenant_id", "purchase_order_id"],
    )
    op.create_index("ix_po_items_tenant_sku", "purchase_order_items", ["tenant_id", "sku_id"])


def downgrade() -> None:
    op.drop_index("ix_po_items_tenant_sku", table_name="purchase_order_items")
    op.drop_index("ix_po_items_tenant_order", table_name="purchase_order_items")
    op.drop_index("ix_po_items_tenant_id", table_name="purchase_order_items")
    op.drop_table("purchase_order_items")
    op.drop_index("ix_purchase_orders_tenant_created", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_tenant_warehouse", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_tenant_supplier", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_tenant_status", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_tenant_id", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index("ix_suppliers_tenant_status", table_name="suppliers")
    op.drop_index("ix_suppliers_tenant_id", table_name="suppliers")
    op.drop_table("suppliers")
