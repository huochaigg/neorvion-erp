"""V12 采购退货、退货出库与供应商退款记录。

Revision ID: 20261011_0018
Revises: 20261010_0017
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261011_0018"
down_revision: str | None = "20261010_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchase_returns",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "purchase_return_no",
            sa.String(length=32),
            nullable=True,
            comment="PRT + 年份 + 6 位 id，租户内唯一，不用 MAX+1",
        ),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "purchase_order_id",
            sa.BigInteger(),
            nullable=False,
            comment="必须关联原采购单，第一版不支持无来源退供应商",
        ),
        sa.Column(
            "warehouse_id",
            sa.BigInteger(),
            nullable=False,
            comment="实际从哪个仓库退给供应商；默认原采购仓，允许改成当前租户启用仓",
        ),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column(
            "settlement_type",
            sa.String(length=16),
            nullable=False,
            comment="REFUND 等待供应商退款；NO_REFUND 出库完成后直接完成",
        ),
        sa.Column(
            "reason",
            sa.String(length=255),
            nullable=False,
            comment="退货原因，例如损坏、质量问题、采购错误",
        ),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column(
            "requested_refund_amount",
            sa.Numeric(12, 2),
            server_default="0",
            nullable=False,
            comment="本次申请供应商退回的金额合计，不等于历史累计已退",
        ),
        sa.Column(
            "approved_refund_amount",
            sa.Numeric(12, 2),
            nullable=True,
            comment="审核最终同意的供应商退款金额，不能超过申请金额",
        ),
        sa.Column(
            "refund_status",
            sa.String(length=16),
            server_default="NONE",
            nullable=False,
            comment="退货单上的退款汇总状态，具体尝试见 supplier_refund_records",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("approved_by", sa.BigInteger(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_by", sa.BigInteger(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.String(length=255), nullable=True),
        sa.Column("outbound_at", sa.DateTime(), nullable=True),
        sa.Column("outbound_by", sa.BigInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "requested_refund_amount >= 0",
            name="ck_purchase_returns_req_refund_nonneg",
        ),
        sa.CheckConstraint(
            "approved_refund_amount IS NULL OR approved_refund_amount >= 0",
            name="ck_purchase_returns_apr_refund_nonneg",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_purchase_returns_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name="fk_purchase_returns_purchase_order",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            name="fk_purchase_returns_supplier",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_purchase_returns_warehouse",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_purchase_returns_created_by"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name="fk_purchase_returns_approved_by"),
        sa.ForeignKeyConstraint(["rejected_by"], ["users.id"], name="fk_purchase_returns_rejected_by"),
        sa.ForeignKeyConstraint(["outbound_by"], ["users.id"], name="fk_purchase_returns_outbound_by"),
        sa.ForeignKeyConstraint(
            ["cancelled_by"],
            ["users.id"],
            name="fk_purchase_returns_cancelled_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_purchase_returns_tenant_id"),
        sa.UniqueConstraint("tenant_id", "purchase_return_no", name="uq_purchase_returns_tenant_no"),
    )
    op.create_index("ix_purchase_returns_tenant_id", "purchase_returns", ["tenant_id"])
    op.create_index("ix_purchase_returns_tenant_status", "purchase_returns", ["tenant_id", "status"])
    op.create_index(
        "ix_purchase_returns_tenant_po",
        "purchase_returns",
        ["tenant_id", "purchase_order_id"],
    )
    op.create_index(
        "ix_purchase_returns_tenant_supplier",
        "purchase_returns",
        ["tenant_id", "supplier_id"],
    )
    op.create_index(
        "ix_purchase_returns_tenant_created",
        "purchase_returns",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "purchase_return_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_return_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "purchase_receipt_item_id",
            sa.BigInteger(),
            nullable=True,
            comment="可选关联某次收货明细，便于追溯；可退数量仍按采购明细累计已收计算",
        ),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "original_received_quantity",
            sa.Integer(),
            nullable=False,
            comment="原采购明细累计实际收货入库数量快照，不等于采购计划数量",
        ),
        sa.Column(
            "requested_return_quantity",
            sa.Integer(),
            nullable=False,
            comment="本次申请退给供应商的数量，不代表历史累计退货",
        ),
        sa.Column(
            "approved_return_quantity",
            sa.Integer(),
            nullable=True,
            comment="审核最终允许退给供应商的数量，不能超过申请退货数量",
        ),
        sa.Column(
            "returned_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="已经真正完成退货出库的累计数量",
        ),
        sa.Column(
            "requested_refund_amount",
            sa.Numeric(12, 2),
            nullable=True,
            comment="本明细申请供应商退回的金额",
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
        sa.CheckConstraint(
            "original_received_quantity >= 0",
            name="ck_prt_items_orig_recv_nonneg",
        ),
        sa.CheckConstraint("requested_return_quantity > 0", name="ck_prt_items_req_return_pos"),
        sa.CheckConstraint(
            "approved_return_quantity IS NULL OR approved_return_quantity >= 0",
            name="ck_prt_items_apr_return_nonneg",
        ),
        sa.CheckConstraint("returned_quantity >= 0", name="ck_prt_items_returned_nonneg"),
        sa.CheckConstraint(
            "requested_refund_amount IS NULL OR requested_refund_amount >= 0",
            name="ck_prt_items_req_refund_nonneg",
        ),
        sa.CheckConstraint(
            "approved_refund_amount IS NULL OR approved_refund_amount >= 0",
            name="ck_prt_items_apr_refund_nonneg",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_prt_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_return_id"],
            ["purchase_returns.tenant_id", "purchase_returns.id"],
            name="fk_prt_items_return",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_item_id"],
            ["purchase_order_items.tenant_id", "purchase_order_items.id"],
            name="fk_prt_items_po_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_prt_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_purchase_return_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "purchase_return_id",
            "purchase_order_item_id",
            name="uq_prt_items_return_po_item",
        ),
    )
    op.create_index("ix_purchase_return_items_tenant_id", "purchase_return_items", ["tenant_id"])
    op.create_index(
        "ix_prt_items_tenant_return",
        "purchase_return_items",
        ["tenant_id", "purchase_return_id"],
    )
    op.create_index(
        "ix_prt_items_tenant_po_item",
        "purchase_return_items",
        ["tenant_id", "purchase_order_item_id"],
    )

    op.create_table(
        "purchase_return_outbounds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "outbound_no",
            sa.String(length=32),
            nullable=True,
            comment="PRO + 年份 + 6 位 id，租户内唯一，不用 MAX+1",
        ),
        sa.Column("purchase_return_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "warehouse_id",
            sa.BigInteger(),
            nullable=False,
            comment="本次出库仓库快照，必须与采购退货单 warehouse_id 一致",
        ),
        sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_pr_outbounds_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_return_id"],
            ["purchase_returns.tenant_id", "purchase_returns.id"],
            name="fk_pr_outbounds_return",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_pr_outbounds_warehouse",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
            name="fk_pr_outbounds_confirmed_by",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_pr_outbounds_created_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pr_outbounds_tenant_id"),
        sa.UniqueConstraint("tenant_id", "outbound_no", name="uq_pr_outbounds_tenant_no"),
    )
    op.create_index("ix_purchase_return_outbounds_tenant_id", "purchase_return_outbounds", ["tenant_id"])
    op.create_index(
        "ix_pr_outbounds_tenant_return",
        "purchase_return_outbounds",
        ["tenant_id", "purchase_return_id"],
    )
    op.create_index(
        "ix_pr_outbounds_tenant_status",
        "purchase_return_outbounds",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_pr_outbounds_tenant_created",
        "purchase_return_outbounds",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "purchase_return_outbound_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_return_outbound_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_return_item_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            comment="本次实际退货出库数量，不是累计已退",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_pr_ob_items_qty_pos"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_pr_ob_items_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_return_outbound_id"],
            ["purchase_return_outbounds.tenant_id", "purchase_return_outbounds.id"],
            name="fk_pr_ob_items_outbound",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_return_item_id"],
            ["purchase_return_items.tenant_id", "purchase_return_items.id"],
            name="fk_pr_ob_items_return_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_pr_ob_items_sku",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_pr_outbound_items_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "purchase_return_outbound_id",
            "purchase_return_item_id",
            name="uq_pr_ob_items_outbound_return_item",
        ),
    )
    op.create_index(
        "ix_purchase_return_outbound_items_tenant_id",
        "purchase_return_outbound_items",
        ["tenant_id"],
    )
    op.create_index(
        "ix_pr_ob_items_tenant_outbound",
        "purchase_return_outbound_items",
        ["tenant_id", "purchase_return_outbound_id"],
    )

    op.create_table(
        "supplier_refund_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("purchase_return_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "refund_no",
            sa.String(length=32),
            nullable=True,
            comment="SRF + 年份 + 6 位 id，租户内唯一",
        ),
        sa.Column(
            "amount",
            sa.Numeric(12, 2),
            nullable=False,
            comment="本次供应商退款金额，不能超过批准剩余可退金额",
        ),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column(
            "external_reference_no",
            sa.String(length=64),
            nullable=True,
            comment="外部银行或供应商付款流水号，本版仅人工记录",
        ),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(),
            nullable=True,
            comment="确认供应商退款到账的时间，确认成功时写入",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_supplier_refunds_amount_nonneg"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_supplier_refunds_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_return_id"],
            ["purchase_returns.tenant_id", "purchase_returns.id"],
            name="fk_supplier_refunds_return",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_supplier_refunds_created_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_supplier_refunds_tenant_id"),
        sa.UniqueConstraint("tenant_id", "refund_no", name="uq_supplier_refunds_tenant_no"),
    )
    op.create_index("ix_supplier_refund_records_tenant_id", "supplier_refund_records", ["tenant_id"])
    op.create_index(
        "ix_supplier_refunds_tenant_return",
        "supplier_refund_records",
        ["tenant_id", "purchase_return_id"],
    )
    op.create_index(
        "ix_supplier_refunds_tenant_status",
        "supplier_refund_records",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_supplier_refunds_tenant_created",
        "supplier_refund_records",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("supplier_refund_records")
    op.drop_table("purchase_return_outbound_items")
    op.drop_table("purchase_return_outbounds")
    op.drop_table("purchase_return_items")
    op.drop_table("purchase_returns")
