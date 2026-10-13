"""销售售后。售后是独立领域，不改 SalesOrderItem.quantity，也不回退销售履约状态。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
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
from app.models.customer import Customer
from app.models.product import ProductSku
from app.models.sales_order import SalesOrder, SalesOrderItem

AFTER_SALE_REFERENCE = "AFTER_SALE"


class AfterSaleType(StrEnum):
    """REFUND_ONLY：仅退款，不要求退回商品。
    RETURN_AND_REFUND：退货入库完成后才退款。
    RETURN_ONLY：只回收库存，不产生退款。
    """

    REFUND_ONLY = "REFUND_ONLY"
    RETURN_AND_REFUND = "RETURN_AND_REFUND"
    RETURN_ONLY = "RETURN_ONLY"


class AfterSaleStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"
    WAITING_RETURN = "WAITING_RETURN"
    WAITING_REFUND = "WAITING_REFUND"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RefundStatus(StrEnum):
    """NONE：本售后类型不需要退款。PENDING：等待人工确认外部退款。
    SUCCESS：已确认退款成功。FAILED 记在 RefundRecord 上，售后仍保持 PENDING。
    """

    NONE = "NONE"
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"


class AfterSaleOrder(TimestampMixin, TenantMixin, Base):
    """一张售后申请。审核前占用可退数量；拒绝/取消后释放占用。"""

    __tablename__ = "after_sale_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_after_sale_orders_tenant_id"),
        UniqueConstraint("tenant_id", "after_sale_no", name="uq_after_sale_orders_tenant_no"),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_after_sale_orders_sales_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_after_sale_orders_customer",
        ),
        CheckConstraint(
            "requested_refund_amount >= 0",
            name="ck_after_sale_orders_req_refund_nonneg",
        ),
        CheckConstraint(
            "approved_refund_amount IS NULL OR approved_refund_amount >= 0",
            name="ck_after_sale_orders_apr_refund_nonneg",
        ),
        Index("ix_after_sale_orders_tenant_status", "tenant_id", "status"),
        Index("ix_after_sale_orders_tenant_sales", "tenant_id", "sales_order_id"),
        Index("ix_after_sale_orders_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    after_sale_no: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="AS + 年份 + 6 位 id，租户内唯一，不用 MAX+1",
    )
    sales_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        comment="REFUND_ONLY / RETURN_AND_REFUND / RETURN_ONLY",
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=AfterSaleStatus.PENDING_APPROVAL.value,
    )
    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="申请原因，例如质量问题、少件补偿",
    )
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        comment="沿用原销售订单币种，本版不允许改",
    )
    requested_refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
        comment="本次申请退款金额合计，不等于历史累计已退",
    )
    approved_refund_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="审核最终同意的退款金额，可能小于申请金额",
    )
    refund_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=RefundStatus.NONE.value,
        comment="售后单上的退款汇总状态，具体尝试见 refund_records",
    )
    requested_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    sales_order: Mapped[SalesOrder] = relationship(
        primaryjoin="AfterSaleOrder.sales_order_id == SalesOrder.id",
        foreign_keys="AfterSaleOrder.sales_order_id",
        viewonly=True,
    )
    customer: Mapped[Customer] = relationship(
        primaryjoin="AfterSaleOrder.customer_id == Customer.id",
        foreign_keys="AfterSaleOrder.customer_id",
        viewonly=True,
    )
    items: Mapped[list[AfterSaleItem]] = relationship(
        "AfterSaleItem",
        back_populates="after_sale_order",
        cascade="all, delete-orphan",
    )


class AfterSaleItem(TimestampMixin, TenantMixin, Base):
    """售后明细。记录原购买数量快照和本次申请，不修改 SalesOrderItem.quantity。"""

    __tablename__ = "after_sale_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_after_sale_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "after_sale_order_id",
            "sales_order_item_id",
            name="uq_after_sale_items_order_so_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "after_sale_order_id"],
            ["after_sale_orders.tenant_id", "after_sale_orders.id"],
            name="fk_after_sale_items_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_item_id"],
            ["sales_order_items.tenant_id", "sales_order_items.id"],
            name="fk_after_sale_items_so_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_after_sale_items_sku",
        ),
        CheckConstraint("original_quantity > 0", name="ck_after_sale_items_orig_pos"),
        CheckConstraint("return_quantity >= 0", name="ck_after_sale_items_return_nonneg"),
        CheckConstraint(
            "approved_return_quantity IS NULL OR approved_return_quantity >= 0",
            name="ck_after_sale_items_apr_return_nonneg",
        ),
        CheckConstraint(
            "requested_refund_amount >= 0",
            name="ck_after_sale_items_req_refund_nonneg",
        ),
        Index("ix_after_sale_items_tenant_order", "tenant_id", "after_sale_order_id"),
        Index("ix_after_sale_items_tenant_so_item", "tenant_id", "sales_order_item_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    after_sale_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sales_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="创建时原销售明细的购买数量快照，不是当前可退数量",
    )
    return_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="本次申请退回的商品数量，不代表历史累计退货",
    )
    approved_return_quantity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="审核最终允许客户退回的数量，可能小于申请退货数量",
    )
    requested_refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        server_default=text("0"),
        comment="本明细申请退款金额，单位沿用原销售订单",
    )
    approved_refund_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="审核最终同意的本明细退款金额",
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    after_sale_order: Mapped[AfterSaleOrder] = relationship(back_populates="items")
    sales_order_item: Mapped[SalesOrderItem] = relationship(
        primaryjoin="AfterSaleItem.sales_order_item_id == SalesOrderItem.id",
        foreign_keys="AfterSaleItem.sales_order_item_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="AfterSaleItem.sku_id == ProductSku.id",
        foreign_keys="AfterSaleItem.sku_id",
        viewonly=True,
    )
