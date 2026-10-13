"""销售出库单。销售订单是卖出什么，出库单是仓库实际发出什么。"""

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
from app.models.product import ProductSku
from app.models.sales_order import SalesOrder, SalesOrderItem

OUTBOUND_ORDER_REFERENCE = "OUTBOUND_ORDER"


class OutboundOrderStatus(StrEnum):
    # 待拣货。出库单刚创建，仓库还没拣完；可改拣货数量或取消（库存仍只是销售预占）。
    PENDING_PICKING = "PENDING_PICKING"
    # 已拣货。仓库已记录实拣数量，尚未扣减实际库存；仍可取消。
    PICKED = "PICKED"
    # 已确认出库。已扣 quantity 并释放预占；终态，不能取消（退货留给后续）。
    CONFIRMED = "CONFIRMED"
    # 已取消。终态；取消时不碰库存（预占仍挂在销售订单上，由订单取消释放）。
    CANCELLED = "CANCELLED"


class OutboundOrder(TimestampMixin, TenantMixin, Base):
    """出库任务。一张销售订单可以有多张出库单，对应多次部分出库。"""

    __tablename__ = "outbound_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_outbound_orders_tenant_id"),
        UniqueConstraint("tenant_id", "outbound_no", name="uq_outbound_orders_tenant_no"),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_outbound_orders_sales",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_outbound_orders_warehouse",
        ),
        Index("ix_outbound_orders_tenant_status", "tenant_id", "status"),
        Index("ix_outbound_orders_tenant_sales", "tenant_id", "sales_order_id"),
        Index("ix_outbound_orders_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    outbound_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sales_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=OutboundOrderStatus.PENDING_PICKING.value,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    picked_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    sales_order: Mapped[SalesOrder] = relationship(
        primaryjoin="OutboundOrder.sales_order_id == SalesOrder.id",
        foreign_keys="OutboundOrder.sales_order_id",
        viewonly=True,
    )
    items: Mapped[list[OutboundOrderItem]] = relationship(
        "OutboundOrderItem",
        back_populates="outbound_order",
        cascade="all, delete-orphan",
    )


class OutboundOrderItem(TimestampMixin, TenantMixin, Base):
    """本次出库明细。拣货不扣库存；确认出库才同时减少 quantity 和 reserved。"""

    __tablename__ = "outbound_order_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ob_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "outbound_order_id",
            "sales_order_item_id",
            name="uq_ob_items_outbound_so_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "outbound_order_id"],
            ["outbound_orders.tenant_id", "outbound_orders.id"],
            name="fk_ob_items_outbound",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_item_id"],
            ["sales_order_items.tenant_id", "sales_order_items.id"],
            name="fk_ob_items_so_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_ob_items_sku",
        ),
        CheckConstraint("planned_quantity > 0", name="ck_ob_items_planned_positive"),
        CheckConstraint("picked_quantity >= 0", name="ck_ob_items_picked_nonneg"),
        CheckConstraint("outbound_quantity >= 0", name="ck_ob_items_outbound_nonneg"),
        CheckConstraint(
            "picked_quantity <= planned_quantity",
            name="ck_ob_items_picked_lte_planned",
        ),
        CheckConstraint(
            "outbound_quantity <= picked_quantity",
            name="ck_ob_items_outbound_lte_picked",
        ),
        Index("ix_ob_items_tenant_outbound", "tenant_id", "outbound_order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    outbound_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sales_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    planned_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    picked_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    outbound_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    outbound_order: Mapped[OutboundOrder] = relationship(back_populates="items")
    sales_order_item: Mapped[SalesOrderItem] = relationship(
        primaryjoin="OutboundOrderItem.sales_order_item_id == SalesOrderItem.id",
        foreign_keys="OutboundOrderItem.sales_order_item_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="OutboundOrderItem.sku_id == ProductSku.id",
        foreign_keys="OutboundOrderItem.sku_id",
        viewonly=True,
    )


class OutboundPick(TimestampMixin, TenantMixin, Base):
    """一次拣货动作。只追加，不覆盖。明细上的 picked_quantity 仍是这些记录的累计。"""

    __tablename__ = "outbound_picks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_outbound_picks_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "outbound_order_id"],
            ["outbound_orders.tenant_id", "outbound_orders.id"],
            name="fk_outbound_picks_outbound",
        ),
        Index("ix_outbound_picks_tenant_outbound", "tenant_id", "outbound_order_id"),
        Index("ix_outbound_picks_tenant_picked_at", "tenant_id", "picked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    outbound_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    picked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    picked_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    outbound_order: Mapped[OutboundOrder] = relationship(
        primaryjoin="OutboundPick.outbound_order_id == OutboundOrder.id",
        foreign_keys="OutboundPick.outbound_order_id",
        viewonly=True,
    )
    lines: Mapped[list[OutboundPickLine]] = relationship(
        "OutboundPickLine",
        back_populates="pick",
        cascade="all, delete-orphan",
        order_by="OutboundPickLine.sku_id",
    )


class OutboundPickLine(TimestampMixin, TenantMixin, Base):
    """一次拣货里某个 SKU 的数量。quantity 是本次，picked_before/after 是累计变化。"""

    __tablename__ = "outbound_pick_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ob_pick_lines_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "pick_id",
            "outbound_order_item_id",
            name="uq_ob_pick_lines_pick_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "pick_id"],
            ["outbound_picks.tenant_id", "outbound_picks.id"],
            name="fk_ob_pick_lines_pick",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "outbound_order_item_id"],
            ["outbound_order_items.tenant_id", "outbound_order_items.id"],
            name="fk_ob_pick_lines_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_ob_pick_lines_sku",
        ),
        CheckConstraint("quantity > 0", name="ck_ob_pick_lines_qty_positive"),
        CheckConstraint("picked_before >= 0", name="ck_ob_pick_lines_before_nonneg"),
        CheckConstraint(
            "picked_after = picked_before + quantity",
            name="ck_ob_pick_lines_after_sum",
        ),
        Index("ix_ob_pick_lines_tenant_pick", "tenant_id", "pick_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pick_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outbound_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    picked_before: Mapped[int] = mapped_column(Integer, nullable=False)
    picked_after: Mapped[int] = mapped_column(Integer, nullable=False)

    pick: Mapped[OutboundPick] = relationship(back_populates="lines")
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="OutboundPickLine.sku_id == ProductSku.id",
        foreign_keys="OutboundPickLine.sku_id",
        viewonly=True,
    )
