"""库存台账与流水。库存维度是 Tenant + Warehouse + SKU，不是 SKU 单独一个数字。"""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.models.product import ProductSku
from app.models.warehouse import Warehouse


class InventoryTransactionType(StrEnum):
    INITIALIZE = "INITIALIZE"
    ADJUST_IN = "ADJUST_IN"
    ADJUST_OUT = "ADJUST_OUT"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class Inventory(TimestampMixin, TenantMixin, Base):
    """当前账面状态。可用库存 = quantity - reserved_quantity，不单独落库。"""

    __tablename__ = "inventories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_inventories_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "warehouse_id",
            "sku_id",
            name="uq_inventories_tenant_warehouse_sku",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_inventories_warehouse",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_inventories_sku",
        ),
        CheckConstraint("quantity >= 0", name="ck_inventories_quantity_nonneg"),
        CheckConstraint("reserved_quantity >= 0", name="ck_inventories_reserved_nonneg"),
        CheckConstraint(
            "reserved_quantity <= quantity",
            name="ck_inventories_reserved_lte_qty",
        ),
        Index("ix_inventories_tenant_warehouse", "tenant_id", "warehouse_id"),
        Index("ix_inventories_tenant_sku", "tenant_id", "sku_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    reserved_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    # 乐观锁版本号。正式调整走 FOR UPDATE；预占用条件 UPDATE；本字段给冲突演示和后续扩展。
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="Inventory.warehouse_id == Warehouse.id",
        foreign_keys="Inventory.warehouse_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="Inventory.sku_id == ProductSku.id",
        foreign_keys="Inventory.sku_id",
        viewonly=True,
    )

    @property
    def available_quantity(self) -> int:
        return self.quantity - self.reserved_quantity


class InventoryTransaction(TenantMixin, Base):
    """库存变化历史。只追加，普通业务不允许改或删。纠错靠新的调整流水。"""

    __tablename__ = "inventory_transactions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "inventory_id"],
            ["inventories.tenant_id", "inventories.id"],
            name="fk_inventory_tx_inventory",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_inventory_tx_warehouse",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_inventory_tx_sku",
        ),
        Index("ix_inventory_tx_tenant_created", "tenant_id", "created_at"),
        Index("ix_inventory_tx_tenant_warehouse", "tenant_id", "warehouse_id"),
        Index("ix_inventory_tx_tenant_sku", "tenant_id", "sku_id"),
        Index("ix_inventory_tx_tenant_type", "tenant_id", "type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    inventory_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    change_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    before_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    after_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    before_reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    after_reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
