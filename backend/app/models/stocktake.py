"""库存盘点。账面快照和实盘数量比较后，确认时按差异调整当前库存。"""

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
from app.models.inventory import Inventory
from app.models.product import ProductSku
from app.models.warehouse import Warehouse

STOCKTAKE_REFERENCE = "STOCKTAKE"


class StocktakeOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    """ 草稿。本版创建后直接进入 COUNTING，保留该值给以后「先建任务再开始」。 """
    COUNTING = "COUNTING"
    """ 盘点中。可填写实盘数量；不锁库存行，避免盘点持续几小时占着数据库锁。 """
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    """ 已提交待确认。普通盘点人员不能再改数量。 """
    CONFIRMED = "CONFIRMED"
    """ 已确认。已按差异调整真实库存；终态，不能取消。 """
    CANCELLED = "CANCELLED" 
    """ 已取消。确认前可以取消；确认后不能。 """


class StocktakeScope(StrEnum):
    ALL = "ALL"
    SELECTED_SKU = "SELECTED_SKU"


class StocktakeOrder(TimestampMixin, TenantMixin, Base):
    """一次盘点任务。创建时只拍账面快照，确认时才改 Inventory。"""

    __tablename__ = "stocktake_orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_stocktake_orders_tenant_id"),
        UniqueConstraint("tenant_id", "stocktake_no", name="uq_stocktake_orders_tenant_no"),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_stocktake_orders_warehouse",
        ),
        Index("ix_stocktake_orders_tenant_status", "tenant_id", "status"),
        Index("ix_stocktake_orders_tenant_warehouse", "tenant_id", "warehouse_id"),
        Index("ix_stocktake_orders_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stocktake_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=StocktakeOrderStatus.COUNTING.value,
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
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

    warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="StocktakeOrder.warehouse_id == Warehouse.id",
        foreign_keys="StocktakeOrder.warehouse_id",
        viewonly=True,
    )
    items: Mapped[list[StocktakeItem]] = relationship(
        "StocktakeItem",
        back_populates="stocktake_order",
        cascade="all, delete-orphan",
    )


class StocktakeItem(TimestampMixin, TenantMixin, Base):
    """盘点明细。system_quantity 是创建时的账面快照，不是确认时的实时库存。"""

    __tablename__ = "stocktake_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_stocktake_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "stocktake_order_id",
            "inventory_id",
            name="uq_stocktake_items_order_inventory",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "stocktake_order_id"],
            ["stocktake_orders.tenant_id", "stocktake_orders.id"],
            name="fk_stocktake_items_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "inventory_id"],
            ["inventories.tenant_id", "inventories.id"],
            name="fk_stocktake_items_inventory",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_stocktake_items_sku",
        ),
        CheckConstraint("system_quantity >= 0", name="ck_stocktake_items_system_nonneg"),
        CheckConstraint(
            "system_reserved_quantity >= 0",
            name="ck_stocktake_items_reserved_nonneg",
        ),
        CheckConstraint(
            "counted_quantity IS NULL OR counted_quantity >= 0",
            name="ck_stocktake_items_counted_nonneg",
        ),
        Index("ix_stocktake_items_tenant_order", "tenant_id", "stocktake_order_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stocktake_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    inventory_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    system_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    system_reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    counted_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difference_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)

    stocktake_order: Mapped[StocktakeOrder] = relationship(back_populates="items")
    inventory: Mapped[Inventory] = relationship(
        primaryjoin="StocktakeItem.inventory_id == Inventory.id",
        foreign_keys="StocktakeItem.inventory_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="StocktakeItem.sku_id == ProductSku.id",
        foreign_keys="StocktakeItem.sku_id",
        viewonly=True,
    )
