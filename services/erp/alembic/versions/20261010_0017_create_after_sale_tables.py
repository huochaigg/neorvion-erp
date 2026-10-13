"""V11 销售售后、退货单与退款记录。

Revision ID: 20261010_0017
Revises: 20261010_0016
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261010_0017"
down_revision: str | None = "20261010_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "after_sale_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "after_sale_no",
            sa.String(length=32),
            nullable=True,
            comment="AS + 年份 + 6 位 id，租户内唯一，不用 MAX+1",
        ),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "type",
            sa.String(length=24),
            nullable=False,
            comment="REFUND_ONLY / RETURN_AND_REFUND / RETURN_ONLY",
        ),
        sa.Column("status", sa.String(length=24), server_default="PENDING_APPROVAL", nullable=False),
        sa.Column(
            "reason",
            sa.String(length=255),
            nullable=False,
            comment="申请原因，例如质量问题、少件补偿",
        ),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column(
            "currency_code",
            sa.String(length=3),
            nullable=False,
            comment="沿用原销售订单币种，本版不允许改",
        ),
        sa.Column(
            "requested_refund_amount",
            sa.Numeric(12, 2),
            server_default="0",
            nullable=False,
            comment="本次申请退款金额合计，不等于历史累计已退",
        ),
        sa.Column(
            "approved_refund_amount",
            sa.Numeric(12, 2),
            nullable=True,
            comment="审核最终同意的退款金额，可能小于申请金额",
        ),
        sa.Column(
            "refund_status",
            sa.String(length=16),
            server_default="NONE",
            nullable=False,
            comment="售后单上的退款汇总状态，具体尝试见 refund_records",
        ),
        sa.Column("requested_by", sa.BigInteger(), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_by", sa.BigInteger(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.String(length=255), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "requested_refund_amount >= 0",
            name="ck_after_sale_orders_req_refund_nonneg",
        ),
        sa.CheckConstraint(
            "approved_refund_amount IS NULL OR approved_refund_amount >= 0",
            name="ck_after_sale_orders_apr_refund_nonneg",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_after_sale_orders_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_after_sale_orders_sales_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_after_sale_orders_customer",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_after_sale_orders_requested_by",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_after_sale_orders_approved_by",
        ),
        sa.ForeignKeyConstraint(
            ["rejected_by"],
            ["users.id"],
            name="fk_after_sale_orders_rejected_by",
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"],
            ["users.id"],
            name="fk_after_sale_orders_cancelled_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_after_sale_orders_tenant_id"),
        sa.UniqueConstraint("tenant_id", "after_sale_no", name="uq_after_sale_orders_tenant_no"),
    )
    op.create_index("ix_after_sale_orders_tenant_id", "after_sale_orders", ["tenant_id"])
    op.create_index(
        "ix_after_sale_orders_tenant_status",
        "after_sale_orders",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_after_sale_orders_tenant_sales",
        "after_sale_orders",
        ["tenant_id", "sales_order_id"],
    )
    op.create_index(
        "ix_after_sale_orders_tenant_created",
        "after_sale_orders",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "after_sale_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("after_sale_order_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "original_quantity",
            sa.Integer(),
            nullable=False,
            comment="创建时原销售明细的购买数量快照，不是当前可退数量",
        ),
        sa.Column(
            "return_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="本次申请退回的商品数量，不代表历史累计退货",
        ),
        sa.Column(
            "approved_return_quantity",
            sa.Integer(),
            nullable=True,
            comment="审核最终允许客户退回的数量，可能小于申请退货数量",
        ),
        sa.Column(
            "requested_refund_amount",
            sa.Numeric(12, 2),
            server_default="0",
            nullable=False,
            comment="本明细申请退款金额，单位沿用原销售订单",
        ),
        sa.Column(
            "approved_refund_amount",
            sa.Numeric(12, 2),
            nullable=True,
            comment="审核最终同意的本明细退款金额",
        ),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("original_quantity > 0", name="ck_after_sale_items_orig_pos"),
        sa.CheckConstraint("return_quantity >= 0", name="ck_after_sale_items_return_nonneg"),
        sa.CheckConstraint(
            "approved_return_quantity IS NULL OR approved_return_quantity >= 0",
            name="ck_after_sale_items_apr_return_nonneg",
        ),
        sa.CheckConstraint(
            "requested_refund_amount >= 0",
            name="ck_after_sale_items_req_refund_nonneg",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_after_sale_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "after_sale_order_id"],
            ["after_sale_orders.tenant_id", "after_sale_orders.id"],
            name="fk_after_sale_items_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_item_id"],
            ["sales_order_items.tenant_id", "sales_order_items.id"],
            name="fk_after_sale_items_so_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_after_sale_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_after_sale_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "after_sale_order_id",
            "sales_order_item_id",
            name="uq_after_sale_items_order_so_item",
        ),
    )
    op.create_index("ix_after_sale_items_tenant_id", "after_sale_items", ["tenant_id"])
    op.create_index(
        "ix_after_sale_items_tenant_order",
        "after_sale_items",
        ["tenant_id", "after_sale_order_id"],
    )
    op.create_index(
        "ix_after_sale_items_tenant_so_item",
        "after_sale_items",
        ["tenant_id", "sales_order_item_id"],
    )

    op.create_table(
        "return_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "return_no",
            sa.String(length=32),
            nullable=True,
            comment="RT + 年份 + 6 位 id，租户内唯一",
        ),
        sa.Column("after_sale_order_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "warehouse_id",
            sa.BigInteger(),
            nullable=False,
            comment="退回仓库，可以和原履约仓不同，但不能跨租户",
        ),
        sa.Column("status", sa.String(length=24), server_default="WAITING_RETURN", nullable=False),
        sa.Column("tracking_no", sa.String(length=64), nullable=True),
        sa.Column("carrier_name", sa.String(length=128), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("received_by", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_return_orders_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "after_sale_order_id"],
            ["after_sale_orders.tenant_id", "after_sale_orders.id"],
            name="fk_return_orders_after_sale",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_return_orders_sales_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_return_orders_warehouse",
        ),
        sa.ForeignKeyConstraint(["received_by"], ["users.id"], name="fk_return_orders_received_by"),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
            name="fk_return_orders_confirmed_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_return_orders_tenant_id"),
        sa.UniqueConstraint("tenant_id", "return_no", name="uq_return_orders_tenant_no"),
        sa.UniqueConstraint(
            "tenant_id",
            "after_sale_order_id",
            name="uq_return_orders_tenant_after_sale",
        ),
    )
    op.create_index("ix_return_orders_tenant_id", "return_orders", ["tenant_id"])
    op.create_index("ix_return_orders_tenant_status", "return_orders", ["tenant_id", "status"])
    op.create_index("ix_return_orders_tenant_created", "return_orders", ["tenant_id", "created_at"])

    op.create_table(
        "return_order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("return_order_id", sa.BigInteger(), nullable=False),
        sa.Column("after_sale_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sales_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "expected_quantity",
            sa.Integer(),
            nullable=False,
            comment="审核通过后预期客户退回的数量",
        ),
        sa.Column(
            "received_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="仓库累计实际收到的退货数量",
        ),
        sa.Column(
            "inbound_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="已确认重新进入普通可售库存的数量",
        ),
        sa.Column(
            "condition",
            sa.String(length=16),
            server_default="GOOD",
            nullable=False,
            comment="退货商品质量。只有 GOOD 默认入普通库存",
        ),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("expected_quantity > 0", name="ck_return_items_expected_pos"),
        sa.CheckConstraint("received_quantity >= 0", name="ck_return_items_received_nonneg"),
        sa.CheckConstraint("inbound_quantity >= 0", name="ck_return_items_inbound_nonneg"),
        sa.CheckConstraint(
            "received_quantity <= expected_quantity",
            name="ck_return_items_received_lte_expected",
        ),
        sa.CheckConstraint(
            "inbound_quantity <= received_quantity",
            name="ck_return_items_inbound_lte_received",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_return_order_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "return_order_id"],
            ["return_orders.tenant_id", "return_orders.id"],
            name="fk_return_order_items_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "after_sale_item_id"],
            ["after_sale_items.tenant_id", "after_sale_items.id"],
            name="fk_return_order_items_as_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sales_order_item_id"],
            ["sales_order_items.tenant_id", "sales_order_items.id"],
            name="fk_return_order_items_so_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_return_order_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_return_order_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "return_order_id",
            "after_sale_item_id",
            name="uq_return_order_items_order_as_item",
        ),
    )
    op.create_index("ix_return_order_items_tenant_id", "return_order_items", ["tenant_id"])
    op.create_index(
        "ix_return_order_items_tenant_order",
        "return_order_items",
        ["tenant_id", "return_order_id"],
    )

    op.create_table(
        "refund_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("after_sale_order_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "refund_no",
            sa.String(length=32),
            nullable=True,
            comment="RF + 年份 + 6 位 id，租户内唯一",
        ),
        sa.Column(
            "amount",
            sa.Numeric(12, 2),
            nullable=False,
            comment="本次退款金额，不能超过售后剩余可退金额",
        ),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column(
            "external_reference_no",
            sa.String(length=64),
            nullable=True,
            comment="外部渠道退款流水号，留给以后对接支付平台",
        ),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_refund_records_amount_nonneg"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_refund_records_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "after_sale_order_id"],
            ["after_sale_orders.tenant_id", "after_sale_orders.id"],
            name="fk_refund_records_after_sale",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_refund_records_created_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_refund_records_tenant_id"),
        sa.UniqueConstraint("tenant_id", "refund_no", name="uq_refund_records_tenant_no"),
    )
    op.create_index("ix_refund_records_tenant_id", "refund_records", ["tenant_id"])
    op.create_index(
        "ix_refund_records_tenant_after_sale",
        "refund_records",
        ["tenant_id", "after_sale_order_id"],
    )
    op.create_index("ix_refund_records_tenant_status", "refund_records", ["tenant_id", "status"])
    op.create_index("ix_refund_records_tenant_created", "refund_records", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_table("refund_records")
    op.drop_table("return_order_items")
    op.drop_table("return_orders")
    op.drop_table("after_sale_items")
    op.drop_table("after_sale_orders")
