"""采购单与明细。采购是计划，审核通过不改库存；收货入库才增加 quantity。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse


class PurchaseOrderStatus(StrEnum):
    """采购单状态。只能经提交 / 审核 / 收货 / 取消流转，不要直接改 status 列。

    审核通过不改库存；收货确认才增加 quantity。
    """

    DRAFT = "DRAFT"
    """草稿。可改供应商、仓库和明细；可提交审核或取消。未入库。"""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    """待审核。可批准进入待收货、驳回，或取消。批准同事务直达待收货，无单独 APPROVED。"""

    WAITING_RECEIPT = "WAITING_RECEIPT"
    """待收货。审核已通过，等待收货入库。可部分收货或一次收完；本版本不可取消。"""

    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    """部分收货。已有收货单入库，但仍有未收完的明细；继续收货直至收完。"""

    RECEIVED = "RECEIVED"
    """已收货。全部明细收齐。终态，不能再流转。"""

    REJECTED = "REJECTED"
    """已驳回。可改单后重新提交，或取消。"""

    CANCELLED = "CANCELLED"
    """已取消。终态，不能再流转。"""


class PurchaseOrder(TimestampMixin, TenantMixin, Base):
    """采购单主表。order_no 在租户内唯一，flush 后按 id 生成。"""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_purchase_orders_tenant_id"),
        UniqueConstraint("tenant_id", "order_no", name="uq_purchase_orders_tenant_order_no"),
        # 复合外键：不能把 A 企业的供应商/仓库挂到 B 企业的采购单上。
        ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            name="fk_purchase_orders_supplier",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_purchase_orders_warehouse",
        ),
        Index("ix_purchase_orders_tenant_status", "tenant_id", "status"),
        Index("ix_purchase_orders_tenant_supplier", "tenant_id", "supplier_id"),
        Index("ix_purchase_orders_tenant_warehouse", "tenant_id", "warehouse_id"),
        Index("ix_purchase_orders_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supplier_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=PurchaseOrderStatus.DRAFT.value,
    )
    expected_arrival_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    supplier: Mapped[Supplier] = relationship(
        primaryjoin="PurchaseOrder.supplier_id == Supplier.id",
        foreign_keys="PurchaseOrder.supplier_id",
        viewonly=True,
    )
    warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="PurchaseOrder.warehouse_id == Warehouse.id",
        foreign_keys="PurchaseOrder.warehouse_id",
        viewonly=True,
    )
    items: Mapped[list[PurchaseOrderItem]] = relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )


class PurchaseOrderItem(TimestampMixin, TenantMixin, Base):
    """采购明细。同一采购单内每个 SKU 只能一行。

    quantity 是计划采购量；收货确认后累加 received_quantity，并增加库存 quantity。
    约束：0 <= received_quantity <= quantity。
    """

    __tablename__ = "purchase_order_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_purchase_order_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "purchase_order_id",
            "sku_id",
            name="uq_po_items_tenant_order_sku",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name="fk_po_items_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_po_items_sku",
        ),
        CheckConstraint("quantity > 0", name="ck_po_items_quantity_positive"),
        CheckConstraint("received_quantity >= 0", name="ck_po_items_received_nonneg"),
        CheckConstraint(
            "received_quantity <= quantity",
            name="ck_po_items_received_lte_qty",
        ),
        Index("ix_po_items_tenant_order", "tenant_id", "purchase_order_id"),
        Index("ix_po_items_tenant_sku", "tenant_id", "sku_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    """所属采购单 id。与 tenant_id 组成复合外键，防止串租户挂单。"""
    purchase_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    """已收货累计数量。收货确认时累加；未收完 = quantity - received_quantity。"""
    received_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """所属采购单。ORM 导航属性，对应 purchase_order_id。"""
    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="PurchaseOrderItem.sku_id == ProductSku.id",
        foreign_keys="PurchaseOrderItem.sku_id",
        viewonly=True,
    )
