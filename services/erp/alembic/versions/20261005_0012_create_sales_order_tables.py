"""V7 客户与销售订单。确认时预占库存，取消待出库时释放。

Revision ID: 20261005_0012
Revises: 20261005_0011
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_0012"
down_revision: str | None = "20261005_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("province", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_customers_tenant"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_customers_tenant_code"),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])
    op.create_index("ix_customers_tenant_status", "customers", ["tenant_id", "status"])

    op.create_table(
        "sales_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("order_no", sa.String(length=32), nullable=True),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="MANUAL"),
        sa.Column("external_order_no", sa.String(length=64), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("recipient_name", sa.String(length=128), nullable=True),
        sa.Column("recipient_phone", sa.String(length=32), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("province", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.BigInteger(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_sales_orders_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_sales_orders_customer",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_sales_orders_warehouse",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_sales_orders_created_by"),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
            name="fk_sales_orders_confirmed_by",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"],
            ["users.id"],
            name="fk_sales_orders_cancelled_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_orders_tenant_id"),
        sa.UniqueConstraint("tenant_id", "order_no", name="uq_sales_orders_tenant_order_no"),
        sa.UniqueConstraint(
            "tenant_id",
            "source",
            "external_order_no",
            name="uq_sales_orders_tenant_source_external",
        ),
    )
    op.create_index("ix_sales_orders_tenant_id", "sales_orders", ["tenant_id"])
    op.create_index("ix_sales_orders_tenant_status", "sales_orders", ["tenant_id", "status"])
    op.create_index("ix_sales_orders_tenant_customer", "sales_orders", ["tenant_id", "customer_id"])
    op.create_index(
        "ix_sales_orders_tenant_warehouse",
        "sales_orders",
        ["tenant_id", "warehouse_id"],
    )
    op.create_index("ix_sales_orders_tenant_created", "sales_orders", ["tenant_id", "created_at"])
    op.create_index("ix_sales_orders_tenant_source", "sales_orders", ["tenant_id", "source"])

    op.create_table(
        "sales_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shipped_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_so_items_quantity_positive"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_so_items_reserved_nonneg"),
        sa.CheckConstraint("shipped_quantity >= 0", name="ck_so_items_shipped_nonneg"),
        sa.CheckConstraint(
            "shipped_quantity <= reserved_quantity",
            name="ck_so_items_shipped_lte_reserved",
        ),
        sa.CheckConstraint("reserved_quantity <= quantity", name="ck_so_items_reserved_lte_qty"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_so_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_so_items_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_so_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_sales_order_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "sales_order_id",
            "sku_id",
            name="uq_so_items_order_sku",
        ),
    )
    op.create_index("ix_so_items_tenant_id", "sales_order_items", ["tenant_id"])
    op.create_index(
        "ix_so_items_tenant_order",
        "sales_order_items",
        ["tenant_id", "sales_order_id"],
    )
    op.create_index("ix_so_items_tenant_sku", "sales_order_items", ["tenant_id", "sku_id"])


def downgrade() -> None:
    op.drop_index("ix_so_items_tenant_sku", table_name="sales_order_items")
    op.drop_index("ix_so_items_tenant_order", table_name="sales_order_items")
    op.drop_index("ix_so_items_tenant_id", table_name="sales_order_items")
    op.drop_table("sales_order_items")
    op.drop_index("ix_sales_orders_tenant_source", table_name="sales_orders")
    op.drop_index("ix_sales_orders_tenant_created", table_name="sales_orders")
    op.drop_index("ix_sales_orders_tenant_warehouse", table_name="sales_orders")
    op.drop_index("ix_sales_orders_tenant_customer", table_name="sales_orders")
    op.drop_index("ix_sales_orders_tenant_status", table_name="sales_orders")
    op.drop_index("ix_sales_orders_tenant_id", table_name="sales_orders")
    op.drop_table("sales_orders")
    op.drop_index("ix_customers_tenant_status", table_name="customers")
    op.drop_index("ix_customers_tenant_id", table_name="customers")
    op.drop_table("customers")
