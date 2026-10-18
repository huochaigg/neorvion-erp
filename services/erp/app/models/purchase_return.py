"""采购退货。独立逆向领域，不修改 PurchaseOrderItem.quantity / received_quantity。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.models.product import ProductSku
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse

PURCHASE_RETURN_REFERENCE = "PURCHASE_RETURN"


class PurchaseReturnSettlementType(StrEnum):
    """REFUND：退货后还要等待供应商返还对应款项。
    NO_REFUND：只记录退货和库存减少，不跟踪供应商退款。
    """

    REFUND = "REFUND"
    NO_REFUND = "NO_REFUND"


class PurchaseReturnStatus(StrEnum):
    """采购退货状态。只能经业务 Action 流转，不要直接 PATCH status。

    审核通过不保留 APPROVED：同事务进入 WAITING_OUTBOUND。
    全部出库后：NO_REFUND 直接 COMPLETED；REFUND 进入 WAITING_REFUND。
    """

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    WAITING_OUTBOUND = "WAITING_OUTBOUND"
    PARTIALLY_RETURNED = "PARTIALLY_RETURNED"
    WAITING_REFUND = "WAITING_REFUND"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PurchaseReturnRefundStatus(StrEnum):
    """NONE：结算类型为 NO_REFUND，或不需要退款。
    PENDING：已退货，等待人工确认供应商退款。
    SUCCESS：批准退款金额已全部确认到账。
    FAILED 记在供应商退款记录上，退货单仍保持 PENDING。
    """

    NONE = "NONE"
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"


class PurchaseReturn(TimestampMixin, TenantMixin, Base):
    """采购退货单。记录计划退给供应商多少，真正扣库存发生在退货出库确认。"""

    __tablename__ = "purchase_returns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_purchase_returns_tenant_id"),
        UniqueConstraint("tenant_id", "purchase_return_no", name="uq_purchase_returns_tenant_no"),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name="fk_purchase_returns_purchase_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            name="fk_purchase_returns_supplier",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_purchase_returns_warehouse",
        ),
        CheckConstraint(
            "requested_refund_amount >= 0",
            name="ck_purchase_returns_req_refund_nonneg",
        ),
        CheckConstraint(
            "approved_refund_amount IS NULL OR approved_refund_amount >= 0",
            name="ck_purchase_returns_apr_refund_nonneg",
        ),
        Index("ix_purchase_returns_tenant_status", "tenant_id", "status"),
        Index("ix_purchase_returns_tenant_po", "tenant_id", "purchase_order_id"),
        Index("ix_purchase_returns_tenant_supplier", "tenant_id", "supplier_id"),
        Index("ix_purchase_returns_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_return_no: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="PRT + 年份 + 6 位 id，租户内唯一，不用 MAX+1",
    )
    supplier_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_order_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="必须关联原采购单，第一版不支持无来源退供应商",
    )
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="实际从哪个仓库退给供应商；默认原采购仓，允许改成当前租户启用仓",
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=PurchaseReturnStatus.DRAFT.value,
    )
    settlement_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="REFUND 等待供应商退款；NO_REFUND 出库完成后直接完成",
    )
    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="退货原因，例如损坏、质量问题、采购错误",
    )
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    requested_refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
        comment="本次申请供应商退回的金额合计，不等于历史累计已退",
    )
    approved_refund_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="审核最终同意的供应商退款金额，不能超过申请金额",
    )
    refund_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=PurchaseReturnRefundStatus.NONE.value,
        comment="退货单上的退款汇总状态，具体尝试见 supplier_refund_records",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outbound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outbound_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    purchase_order: Mapped[PurchaseOrder] = relationship(
        primaryjoin="PurchaseReturn.purchase_order_id == PurchaseOrder.id",
        foreign_keys="PurchaseReturn.purchase_order_id",
        viewonly=True,
    )
    supplier: Mapped[Supplier] = relationship(
        primaryjoin="PurchaseReturn.supplier_id == Supplier.id",
        foreign_keys="PurchaseReturn.supplier_id",
        viewonly=True,
    )
    warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="PurchaseReturn.warehouse_id == Warehouse.id",
        foreign_keys="PurchaseReturn.warehouse_id",
        viewonly=True,
    )
    items: Mapped[list[PurchaseReturnItem]] = relationship(
        "PurchaseReturnItem",
        back_populates="purchase_return",
        cascade="all, delete-orphan",
    )


class PurchaseReturnItem(TimestampMixin, TenantMixin, Base):
    """采购退货明细。记录已收货快照和本次申请，不修改原采购明细数量。"""

    __tablename__ = "purchase_return_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_purchase_return_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "purchase_return_id",
            "purchase_order_item_id",
            name="uq_prt_items_return_po_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_return_id"],
            ["purchase_returns.tenant_id", "purchase_returns.id"],
            name="fk_prt_items_return",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_item_id"],
            ["purchase_order_items.tenant_id", "purchase_order_items.id"],
            name="fk_prt_items_po_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_prt_items_sku",
        ),
        CheckConstraint(
            "original_received_quantity >= 0",
            name="ck_prt_items_orig_recv_nonneg",
        ),
        CheckConstraint(
            "requested_return_quantity > 0",
            name="ck_prt_items_req_return_pos",
        ),
        CheckConstraint(
            "approved_return_quantity IS NULL OR approved_return_quantity >= 0",
            name="ck_prt_items_apr_return_nonneg",
        ),
        CheckConstraint(
            "returned_quantity >= 0",
            name="ck_prt_items_returned_nonneg",
        ),
        CheckConstraint(
            "requested_refund_amount IS NULL OR requested_refund_amount >= 0",
            name="ck_prt_items_req_refund_nonneg",
        ),
        CheckConstraint(
            "approved_refund_amount IS NULL OR approved_refund_amount >= 0",
            name="ck_prt_items_apr_refund_nonneg",
        ),
        Index("ix_prt_items_tenant_return", "tenant_id", "purchase_return_id"),
        Index("ix_prt_items_tenant_po_item", "tenant_id", "purchase_order_item_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_return_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_receipt_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="可选关联某次收货明细，便于追溯；可退数量仍按采购明细累计已收计算",
    )
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_received_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="原采购明细累计实际收货入库数量快照，不等于采购计划数量",
    )
    requested_return_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="本次申请退给供应商的数量，不代表历史累计退货",
    )
    approved_return_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="审核最终允许退给供应商的数量，不能超过申请退货数量",
    )
    returned_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="已经真正完成退货出库的累计数量",
    )
    requested_refund_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="本明细申请供应商退回的金额",
    )
    approved_refund_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="审核最终同意的本明细退款金额",
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    purchase_return: Mapped[PurchaseReturn] = relationship(back_populates="items")
    purchase_order_item: Mapped[PurchaseOrderItem] = relationship(
        primaryjoin="PurchaseReturnItem.purchase_order_item_id == PurchaseOrderItem.id",
        foreign_keys="PurchaseReturnItem.purchase_order_item_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="PurchaseReturnItem.sku_id == ProductSku.id",
        foreign_keys="PurchaseReturnItem.sku_id",
        viewonly=True,
    )
