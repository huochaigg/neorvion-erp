"""采购收货单。采购单是计划，收货单是实际到货；确认收货才增加库存。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.models.product import ProductSku
from app.models.purchase import PurchaseOrder, PurchaseOrderItem

PURCHASE_RECEIPT_REFERENCE = "PURCHASE_RECEIPT"


class PurchaseReceiptStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class PurchaseReceipt(TimestampMixin, TenantMixin, Base):
    """收货单。仓库固定为采购单仓库，确认前不改库存、不改已收数量。"""

    __tablename__ = "purchase_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_purchase_receipts_tenant_id"),
        UniqueConstraint("tenant_id", "receipt_no", name="uq_purchase_receipts_tenant_no"),
        # 复合外键：不能把别的企业的采购单或仓库挂到本收货单。
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name="fk_purchase_receipts_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_purchase_receipts_warehouse",
        ),
        Index("ix_purchase_receipts_tenant_status", "tenant_id", "status"),
        Index("ix_purchase_receipts_tenant_order", "tenant_id", "purchase_order_id"),
        Index("ix_purchase_receipts_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 收货单号，在租户内唯一，flush 后按 id 生成。
    receipt_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purchase_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=PurchaseReceiptStatus.DRAFT.value,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 采购单，只读。
    purchase_order: Mapped[PurchaseOrder] = relationship(
        primaryjoin="PurchaseReceipt.purchase_order_id == PurchaseOrder.id",
        foreign_keys="PurchaseReceipt.purchase_order_id",
        viewonly=True,
    )
    items: Mapped[list[PurchaseReceiptItem]] = relationship(
        "PurchaseReceiptItem",
        back_populates="receipt",
        cascade="all, delete-orphan",
    )


class PurchaseReceiptItem(TimestampMixin, TenantMixin, Base):
    """本次收货明细。expected 是建单时的剩余待收，received 是本次实收。"""

    __tablename__ = "purchase_receipt_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_pr_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "purchase_receipt_id",
            "purchase_order_item_id",
            name="uq_pr_items_receipt_po_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_receipt_id"],
            ["purchase_receipts.tenant_id", "purchase_receipts.id"],
            name="fk_pr_items_receipt",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_item_id"],
            ["purchase_order_items.tenant_id", "purchase_order_items.id"],
            name="fk_pr_items_po_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_pr_items_sku",
        ),
        CheckConstraint("expected_quantity > 0", name="ck_pr_items_expected_positive"),
        CheckConstraint("received_quantity > 0", name="ck_pr_items_received_positive"),
        CheckConstraint(
            "received_quantity <= expected_quantity",
            name="ck_pr_items_received_lte_expected",
        ),
        Index("ix_pr_items_tenant_receipt", "tenant_id", "purchase_receipt_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_receipt_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    received_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    receipt: Mapped[PurchaseReceipt] = relationship(back_populates="items")
    purchase_order_item: Mapped[PurchaseOrderItem] = relationship(
        primaryjoin="PurchaseReceiptItem.purchase_order_item_id == PurchaseOrderItem.id",
        foreign_keys="PurchaseReceiptItem.purchase_order_item_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="PurchaseReceiptItem.sku_id == ProductSku.id",
        foreign_keys="PurchaseReceiptItem.sku_id",
        viewonly=True,
    )
