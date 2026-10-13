"""物流单。出库表示货离开库存账面，发货表示货交给承运商，两者不是同一时刻。"""

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.models.carrier import Carrier
from app.models.outbound import OutboundOrder, OutboundOrderItem
from app.models.product import ProductSku
from app.models.sales_order import SalesOrder, SalesOrderItem


class ShipmentStatus(StrEnum):
    # 物流单状态
    # 草稿
    DRAFT = "DRAFT"
    # 已发货
    SHIPPED = "SHIPPED"
    # 在途中
    IN_TRANSIT = "IN_TRANSIT"
    # 已签收
    DELIVERED = "DELIVERED"
    # 已取消
    CANCELLED = "CANCELLED"


class TrackingEventStatus(StrEnum):
    # 物流轨迹状态
    # 揽收
    PICKED_UP = "PICKED_UP"
    # 在途中
    IN_TRANSIT = "IN_TRANSIT"
    # 到达分拨中心
    ARRIVED_AT_HUB = "ARRIVED_AT_HUB"
    # 派送中
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    # 已签收
    DELIVERED = "DELIVERED"
    # 异常
    EXCEPTION = "EXCEPTION"
    # 其他
    OTHER = "OTHER"


class Shipment(TimestampMixin, TenantMixin, Base):
    """一次交给承运商的包裹。V9 一张物流单对应一张出库单，以后可扩展合并发货。"""

    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_shipments_tenant_id"),
        UniqueConstraint("tenant_id", "shipment_no", name="uq_shipments_tenant_no"),
        # 运单号按承运商区分。不同公司可能出现相同格式的号码。
        UniqueConstraint(
            "tenant_id",
            "carrier_id",
            "tracking_no",
            name="uq_shipments_tenant_carrier_tracking",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_id"],
            ["sales_orders.tenant_id", "sales_orders.id"],
            name="fk_shipments_sales",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "outbound_order_id"],
            ["outbound_orders.tenant_id", "outbound_orders.id"],
            name="fk_shipments_outbound",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "carrier_id"],
            ["carriers.tenant_id", "carriers.id"],
            name="fk_shipments_carrier",
        ),
        Index("ix_shipments_tenant_status", "tenant_id", "status"),
        Index("ix_shipments_tenant_sales", "tenant_id", "sales_order_id"),
        Index("ix_shipments_tenant_outbound", "tenant_id", "outbound_order_id"),
        Index("ix_shipments_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shipment_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sales_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outbound_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    carrier_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tracking_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=ShipmentStatus.DRAFT.value,
    )
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shipped_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    sales_order: Mapped[SalesOrder] = relationship(
        primaryjoin="Shipment.sales_order_id == SalesOrder.id",
        foreign_keys="Shipment.sales_order_id",
        viewonly=True,
    )
    outbound_order: Mapped[OutboundOrder] = relationship(
        primaryjoin="Shipment.outbound_order_id == OutboundOrder.id",
        foreign_keys="Shipment.outbound_order_id",
        viewonly=True,
    )
    carrier: Mapped[Carrier] = relationship(
        primaryjoin="Shipment.carrier_id == Carrier.id",
        foreign_keys="Shipment.carrier_id",
        viewonly=True,
    )
    items: Mapped[list[ShipmentItem]] = relationship(
        "ShipmentItem",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentItem.sku_id",
    )
    tracking_events: Mapped[list[ShipmentTrackingEvent]] = relationship(
        "ShipmentTrackingEvent",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentTrackingEvent.occurred_at, ShipmentTrackingEvent.id",
    )


class ShipmentItem(TimestampMixin, TenantMixin, Base):
    """本物流单实际发给承运商的数量。同一出库明细可以拆成多个包裹。"""

    __tablename__ = "shipment_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_shipment_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "shipment_id",
            "outbound_order_item_id",
            name="uq_shipment_items_shipment_ob_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "shipment_id"],
            ["shipments.tenant_id", "shipments.id"],
            name="fk_shipment_items_shipment",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "outbound_order_item_id"],
            ["outbound_order_items.tenant_id", "outbound_order_items.id"],
            name="fk_shipment_items_ob_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sales_order_item_id"],
            ["sales_order_items.tenant_id", "sales_order_items.id"],
            name="fk_shipment_items_so_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_shipment_items_sku",
        ),
        CheckConstraint("quantity > 0", name="ck_shipment_items_qty_positive"),
        Index("ix_shipment_items_tenant_shipment", "tenant_id", "shipment_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outbound_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sales_order_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    shipment: Mapped[Shipment] = relationship(back_populates="items")
    outbound_order_item: Mapped[OutboundOrderItem] = relationship(
        primaryjoin="ShipmentItem.outbound_order_item_id == OutboundOrderItem.id",
        foreign_keys="ShipmentItem.outbound_order_item_id",
        viewonly=True,
    )
    sales_order_item: Mapped[SalesOrderItem] = relationship(
        primaryjoin="ShipmentItem.sales_order_item_id == SalesOrderItem.id",
        foreign_keys="ShipmentItem.sales_order_item_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="ShipmentItem.sku_id == ProductSku.id",
        foreign_keys="ShipmentItem.sku_id",
        viewonly=True,
    )


class ShipmentTrackingEvent(TenantMixin, Base):
    """物流轨迹。只追加，不提供普通编辑删除。错误时再写一条纠正事件。"""

    __tablename__ = "shipment_tracking_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_shipment_tracking_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "shipment_id"],
            ["shipments.tenant_id", "shipments.id"],
            name="fk_shipment_tracking_shipment",
        ),
        Index("ix_shipment_tracking_tenant_shipment", "tenant_id", "shipment_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    shipment: Mapped[Shipment] = relationship(back_populates="tracking_events")
