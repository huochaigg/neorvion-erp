"""V9 物流发货。出库状态与已出库数量改名，新增物流商和物流单。

Revision ID: 20261008_0015
Revises: 20261006_0014
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_0015"
down_revision: str | None = "20261006_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # V8 的 shipped_quantity 实际是仓库已出库。V9 把物流已发货留给 shipped_quantity。
    # 不重建明细表：先加 outbound_quantity，拷贝旧值，再把 shipped 清零。
    op.add_column(
        "sales_order_items",
        sa.Column(
            "outbound_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute("UPDATE sales_order_items SET outbound_quantity = shipped_quantity")
    op.execute("UPDATE sales_order_items SET shipped_quantity = 0")
    op.drop_constraint(
        "ck_so_items_reserved_plus_shipped",
        "sales_order_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_so_items_outbound_nonneg",
        "sales_order_items",
        "outbound_quantity >= 0",
    )
    op.create_check_constraint(
        "ck_so_items_reserved_plus_outbound",
        "sales_order_items",
        "reserved_quantity + outbound_quantity <= quantity",
    )
    op.create_check_constraint(
        "ck_so_items_shipped_lte_outbound",
        "sales_order_items",
        "shipped_quantity <= outbound_quantity",
    )
    # V8 把 PARTIALLY_SHIPPED / SHIPPED 当成出库。历史开发数据没有真实物流，直接改名。
    op.execute(
        "UPDATE sales_orders SET status = 'PARTIALLY_OUTBOUND' "
        "WHERE status = 'PARTIALLY_SHIPPED'"
    )
    op.execute("UPDATE sales_orders SET status = 'OUTBOUNDED' WHERE status = 'SHIPPED'")

    op.create_table(
        "carriers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.Column("carrier_type", sa.String(length=32), nullable=False),
        sa.Column("contact_name", sa.String(length=64), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_carriers_tenant"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_carriers_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_carriers_tenant_code"),
    )
    op.create_index("ix_carriers_tenant_id", "carriers", ["tenant_id"])
    op.create_index("ix_carriers_tenant_status", "carriers", ["tenant_id", "status"])

    op.create_table(
        "shipments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("shipment_no", sa.String(length=32), nullable=True),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("outbound_order_id", sa.BigInteger(), nullable=False),
        sa.Column("carrier_id", sa.BigInteger(), nullable=False),
        sa.Column("tracking_no", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("shipped_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("shipped_by", sa.BigInteger(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_shipments_tenant"),
        sa.ForeignKeyConstraint(["shipped_by"], ["users.id"], name="fk_shipments_shipped_by"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_shipments_created_by"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_shipments_sales",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outbound_order_id"],
            ["outbound_orders.tenant_id", "outbound_orders.id"],
            name="fk_shipments_outbound",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "carrier_id"],
            ["carriers.tenant_id", "carriers.id"],
            name="fk_shipments_carrier",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_shipments_tenant_id"),
        sa.UniqueConstraint("tenant_id", "shipment_no", name="uq_shipments_tenant_no"),
        sa.UniqueConstraint(
            "tenant_id",
            "carrier_id",
            "tracking_no",
            name="uq_shipments_tenant_carrier_tracking",
        ),
    )
    op.create_index("ix_shipments_tenant_id", "shipments", ["tenant_id"])
    op.create_index("ix_shipments_tenant_status", "shipments", ["tenant_id", "status"])
    op.create_index("ix_shipments_tenant_sales", "shipments", ["tenant_id", "sales_order_id"])
    op.create_index(
        "ix_shipments_tenant_outbound",
        "shipments",
        ["tenant_id", "outbound_order_id"],
    )
    op.create_index("ix_shipments_tenant_created", "shipments", ["tenant_id", "created_at"])

    op.create_table(
        "shipment_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("shipment_id", sa.BigInteger(), nullable=False),
        sa.Column("outbound_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_shipment_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "shipment_id"],
            ["shipments.tenant_id", "shipments.id"],
            name="fk_shipment_items_shipment",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "outbound_order_item_id"],
            ["outbound_order_items.tenant_id", "outbound_order_items.id"],
            name="fk_shipment_items_ob_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_item_id"],
            ["sales_order_items.tenant_id", "sales_order_items.id"],
            name="fk_shipment_items_so_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_shipment_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_shipment_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "shipment_id",
            "outbound_order_item_id",
            name="uq_shipment_items_shipment_ob_item",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_shipment_items_qty_positive"),
    )
    op.create_index("ix_shipment_items_tenant_id", "shipment_items", ["tenant_id"])
    op.create_index(
        "ix_shipment_items_tenant_shipment",
        "shipment_items",
        ["tenant_id", "shipment_id"],
    )

    op.create_table(
        "shipment_tracking_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("shipment_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_shipment_tracking_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_shipment_tracking_user",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "shipment_id"],
            ["shipments.tenant_id", "shipments.id"],
            name="fk_shipment_tracking_shipment",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_shipment_tracking_tenant_id"),
    )
    op.create_index(
        "ix_shipment_tracking_tenant_id",
        "shipment_tracking_events",
        ["tenant_id"],
    )
    op.create_index(
        "ix_shipment_tracking_tenant_shipment",
        "shipment_tracking_events",
        ["tenant_id", "shipment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_shipment_tracking_tenant_shipment", table_name="shipment_tracking_events")
    op.drop_index("ix_shipment_tracking_tenant_id", table_name="shipment_tracking_events")
    op.drop_table("shipment_tracking_events")
    op.drop_index("ix_shipment_items_tenant_shipment", table_name="shipment_items")
    op.drop_index("ix_shipment_items_tenant_id", table_name="shipment_items")
    op.drop_table("shipment_items")
    op.drop_index("ix_shipments_tenant_created", table_name="shipments")
    op.drop_index("ix_shipments_tenant_outbound", table_name="shipments")
    op.drop_index("ix_shipments_tenant_sales", table_name="shipments")
    op.drop_index("ix_shipments_tenant_status", table_name="shipments")
    op.drop_index("ix_shipments_tenant_id", table_name="shipments")
    op.drop_table("shipments")
    op.drop_index("ix_carriers_tenant_status", table_name="carriers")
    op.drop_index("ix_carriers_tenant_id", table_name="carriers")
    op.drop_table("carriers")
    op.execute(
        "UPDATE sales_orders SET status = 'PARTIALLY_SHIPPED' "
        "WHERE status = 'PARTIALLY_OUTBOUND'"
    )
    op.execute("UPDATE sales_orders SET status = 'SHIPPED' WHERE status = 'OUTBOUNDED'")
    op.execute("UPDATE sales_order_items SET shipped_quantity = outbound_quantity")
    op.drop_constraint("ck_so_items_shipped_lte_outbound", "sales_order_items", type_="check")
    op.drop_constraint("ck_so_items_reserved_plus_outbound", "sales_order_items", type_="check")
    op.drop_constraint("ck_so_items_outbound_nonneg", "sales_order_items", type_="check")
    op.create_check_constraint(
        "ck_so_items_reserved_plus_shipped",
        "sales_order_items",
        "reserved_quantity + shipped_quantity <= quantity",
    )
    op.drop_column("sales_order_items", "outbound_quantity")
