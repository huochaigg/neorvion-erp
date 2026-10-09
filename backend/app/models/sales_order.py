"""销售订单与明细。确认后只预占库存，不减少实际 quantity。出库留给后续版本。"""

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
from app.models.warehouse import Warehouse

# 库存流水用这个值区分「这次预占来自哪张销售订单」。
SALES_ORDER_REFERENCE = "SALES_ORDER"


class SalesOrderStatus(StrEnum):
    """销售订单状态。只能经提交 / 确认 / 取消流转，不要直接改 status 列。"""

    """草稿。可改客户、仓库、收货信息和明细；可提交或取消。未预占库存。"""
    DRAFT = "DRAFT"

    """待确认。已提交、等待审核。确认才会预占库存；也可取消且不动库存。"""
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"

    """待出库。已确认并预占。尚未正式出库时可以整单取消并释放预占。"""
    WAITING_OUTBOUND = "WAITING_OUTBOUND"

    """部分出库。已经扣过库存，不能整单取消。"""
    PARTIALLY_OUTBOUND = "PARTIALLY_OUTBOUND"

    """已出库。购买数量都已离开库存账面，尚未全部交给承运商。"""
    OUTBOUNDED = "OUTBOUNDED"

    """部分发货。已经有物流单确认发货。"""
    PARTIALLY_SHIPPED = "PARTIALLY_SHIPPED"

    """已发货。订单数量都已交给承运商。"""
    SHIPPED = "SHIPPED"

    """已完成。全部物流单都已签收。"""
    COMPLETED = "COMPLETED"

    """已取消。终态，不能再流转。"""
    CANCELLED = "CANCELLED"


class SalesOrderSource(StrEnum):
    """来源只做标记。V7 不连接 Amazon / Shopify / TikTok。"""

    MANUAL = "MANUAL"
    AMAZON = "AMAZON"
    SHOPIFY = "SHOPIFY"
    TIKTOK = "TIKTOK"
    OTHER = "OTHER"


class SalesOrder(TimestampMixin, TenantMixin, Base):
    """销售订单主表。

    recipient_* 是下单当时的收货快照，不是 Customer 的实时地址。
    客户以后改档案，已保存的订单仍显示当时的收件人和地址。
    """

    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_sales_orders_tenant_id"),
        UniqueConstraint("tenant_id", "order_no", name="uq_sales_orders_tenant_order_no"),
        # 平台单号可空。MySQL 唯一索引把 NULL 当成互不相等，手工单可以都不填。
        UniqueConstraint(
            "tenant_id",
            "source",
            "external_order_no",
            name="uq_sales_orders_tenant_source_external",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_sales_orders_customer",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_sales_orders_warehouse",
        ),
        Index("ix_sales_orders_tenant_status", "tenant_id", "status"),
        Index("ix_sales_orders_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_sales_orders_tenant_warehouse", "tenant_id", "warehouse_id"),
        Index("ix_sales_orders_tenant_created", "tenant_id", "created_at"),
        Index("ix_sales_orders_tenant_source", "tenant_id", "source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=SalesOrderStatus.DRAFT.value,
    )
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=SalesOrderSource.MANUAL.value,
    )
    external_order_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        server_default="CNY",
    )
    recipient_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
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

    customer: Mapped[Customer] = relationship(
        primaryjoin="SalesOrder.customer_id == Customer.id",
        foreign_keys="SalesOrder.customer_id",
        viewonly=True,
    )
    warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="SalesOrder.warehouse_id == Warehouse.id",
        foreign_keys="SalesOrder.warehouse_id",
        viewonly=True,
    )
    items: Mapped[list[SalesOrderItem]] = relationship(
        "SalesOrderItem",
        back_populates="sales_order",
        cascade="all, delete-orphan",
    )


class SalesOrderItem(TimestampMixin, TenantMixin, Base):
    """销售明细。

    reserved_quantity：尚未出库的预占。
    outbound_quantity：累计仓库已出库。
    shipped_quantity：累计已交给承运商。
    """

    __tablename__ = "sales_order_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_sales_order_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "sales_order_id",
            "sku_id",
            name="uq_so_items_order_sku",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_so_items_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_so_items_sku",
        ),
        CheckConstraint("quantity > 0", name="ck_so_items_quantity_positive"),
        CheckConstraint("reserved_quantity >= 0", name="ck_so_items_reserved_nonneg"),
        CheckConstraint("outbound_quantity >= 0", name="ck_so_items_outbound_nonneg"),
        CheckConstraint("shipped_quantity >= 0", name="ck_so_items_shipped_nonneg"),
        # 预占尚未出库 + 已出库 不能超过购买数量。
        CheckConstraint(
            "reserved_quantity + outbound_quantity <= quantity",
            name="ck_so_items_reserved_plus_outbound",
        ),
        # 交给承运商的数量不能超过已经出库的数量。
        CheckConstraint(
            "shipped_quantity <= outbound_quantity",
            name="ck_so_items_shipped_lte_outbound",
        ),
        Index("ix_so_items_tenant_order", "tenant_id", "sales_order_id"),
        Index("ix_so_items_tenant_sku", "tenant_id", "sku_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sales_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    reserved_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    outbound_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    shipped_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sales_order: Mapped[SalesOrder] = relationship(back_populates="items")
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="SalesOrderItem.sku_id == ProductSku.id",
        foreign_keys="SalesOrderItem.sku_id",
        viewonly=True,
    )
