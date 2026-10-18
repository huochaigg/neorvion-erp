"""销售退货单。收到退货不等于入库；只有 GOOD 才进入普通 Inventory.quantity。"""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.models.after_sale import AfterSaleItem, AfterSaleOrder
from app.models.product import ProductSku
from app.models.sales_order import SalesOrder, SalesOrderItem
from app.models.warehouse import Warehouse

RETURN_ORDER_REFERENCE = "RETURN_ORDER"


class ReturnOrderStatus(StrEnum):
    WAITING_RETURN = "WAITING_RETURN"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    PARTIALLY_INBOUNDED = "PARTIALLY_INBOUNDED"
    INBOUNDED = "INBOUNDED"
    CANCELLED = "CANCELLED"


class ReturnCondition(StrEnum):
    """GOOD：可重新入普通库存。DAMAGED / UNSELLABLE：可记已收，默认不入普通库存。"""

    GOOD = "GOOD"
    DAMAGED = "DAMAGED"
    UNSELLABLE = "UNSELLABLE"
    OTHER = "OTHER"


class ReturnOrder(TimestampMixin, TenantMixin, Base):
    """退货单。审核通过后为需要退货的售后创建；一张售后对应一张退货单。"""

    __tablename__ = "return_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_return_orders_tenant_id"),
        UniqueConstraint("tenant_id", "return_no", name="uq_return_orders_tenant_no"),
        UniqueConstraint(
            "tenant_id",
            "after_sale_order_id",
            name="uq_return_orders_tenant_after_sale",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "after_sale_order_id"],
            ["after_sale_orders.tenant_id", "after_sale_orders.id"],
            name="fk_return_orders_after_sale",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_return_orders_sales_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_return_orders_warehouse",
        ),
        Index("ix_return_orders_tenant_status", "tenant_id", "status"),
        Index("ix_return_orders_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    return_no: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="RT + 年份 + 6 位 id，租户内唯一",
    )
    after_sale_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sales_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="退回仓库，可以和原履约仓不同，但不能跨租户",
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=ReturnOrderStatus.WAITING_RETURN.value,
    )
    tracking_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    carrier_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    after_sale_order: Mapped[AfterSaleOrder] = relationship(
        primaryjoin="ReturnOrder.after_sale_order_id == AfterSaleOrder.id",
        foreign_keys="ReturnOrder.after_sale_order_id",
        viewonly=True,
    )
    sales_order: Mapped[SalesOrder] = relationship(
        primaryjoin="ReturnOrder.sales_order_id == SalesOrder.id",
        foreign_keys="ReturnOrder.sales_order_id",
        viewonly=True,
    )
    warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="ReturnOrder.warehouse_id == Warehouse.id",
        foreign_keys="ReturnOrder.warehouse_id",
        viewonly=True,
    )
    items: Mapped[list[ReturnOrderItem]] = relationship(
        "ReturnOrderItem",
        back_populates="return_order",
        cascade="all, delete-orphan",
    )


class ReturnOrderItem(TimestampMixin, TenantMixin, Base):
    """退货明细。expected 来自审核批准数量；received 是仓库实收；inbound 才入普通库存。"""

    __tablename__ = "return_order_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_return_order_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "return_order_id",
            "after_sale_item_id",
            name="uq_return_order_items_order_as_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "return_order_id"],
            ["return_orders.tenant_id", "return_orders.id"],
            name="fk_return_order_items_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "after_sale_item_id"],
            ["after_sale_items.tenant_id", "after_sale_items.id"],
            name="fk_return_order_items_as_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_item_id"],
            ["sales_order_items.tenant_id", "sales_order_items.id"],
            name="fk_return_order_items_so_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_return_order_items_sku",
        ),
        CheckConstraint("expected_quantity > 0", name="ck_return_items_expected_pos"),
        CheckConstraint("received_quantity >= 0", name="ck_return_items_received_nonneg"),
        CheckConstraint("inbound_quantity >= 0", name="ck_return_items_inbound_nonneg"),
        CheckConstraint(
            "received_quantity <= expected_quantity",
            name="ck_return_items_received_lte_expected",
        ),
        CheckConstraint(
            "inbound_quantity <= received_quantity",
            name="ck_return_items_inbound_lte_received",
        ),
        Index("ix_return_order_items_tenant_order", "tenant_id", "return_order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    return_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    after_sale_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sales_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="审核通过后预期客户退回的数量",
    )
    received_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="仓库累计实际收到的退货数量",
    )
    inbound_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="已确认重新进入普通可售库存的数量",
    )
    condition: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=ReturnCondition.GOOD.value,
        comment="退货商品质量。只有 GOOD 默认入普通库存",
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)

    return_order: Mapped[ReturnOrder] = relationship(back_populates="items")
    after_sale_item: Mapped[AfterSaleItem] = relationship(
        primaryjoin="ReturnOrderItem.after_sale_item_id == AfterSaleItem.id",
        foreign_keys="ReturnOrderItem.after_sale_item_id",
        viewonly=True,
    )
    sales_order_item: Mapped[SalesOrderItem] = relationship(
        primaryjoin="ReturnOrderItem.sales_order_item_id == SalesOrderItem.id",
        foreign_keys="ReturnOrderItem.sales_order_item_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="ReturnOrderItem.sku_id == ProductSku.id",
        foreign_keys="ReturnOrderItem.sku_id",
        viewonly=True,
    )
