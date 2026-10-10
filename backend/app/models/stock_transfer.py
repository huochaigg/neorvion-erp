"""库存调拨。同一租户两个仓库之间移动库存；调出和调入拆成两个事务。"""

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
from app.models.warehouse import Warehouse

STOCK_TRANSFER_REFERENCE = "STOCK_TRANSFER"


class StockTransferStatus(StrEnum):
    # 草稿。可改仓库和明细；不改库存。库存不足也可以先保存。
    DRAFT = "DRAFT"
    # 待调出。核心字段锁定；确认调出才扣源仓库存。
    PENDING_OUTBOUND = "PENDING_OUTBOUND"
    # 在途。源仓已扣减，目标仓尚未增加。货物不属于任一仓库存。
    IN_TRANSIT = "IN_TRANSIT"
    # 已完成。目标仓已增加。终态。
    COMPLETED = "COMPLETED"
    # 已取消。仅草稿和待调出可取消；在途后货物已离源仓，不能普通取消。
    CANCELLED = "CANCELLED"


class StockTransfer(TimestampMixin, TenantMixin, Base):
    """跨仓库调拨单。不支持跨租户；跨公司应走采购/销售。"""

    __tablename__ = "stock_transfers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_stock_transfers_tenant_id"),
        UniqueConstraint("tenant_id", "transfer_no", name="uq_stock_transfers_tenant_no"),
        ForeignKeyConstraint(
            ["tenant_id", "source_warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_stock_transfers_source",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "target_warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_stock_transfers_target",
        ),
        CheckConstraint(
            "source_warehouse_id <> target_warehouse_id",
            name="ck_stock_transfers_distinct_warehouses",
        ),
        Index("ix_stock_transfers_tenant_status", "tenant_id", "status"),
        Index("ix_stock_transfers_tenant_source", "tenant_id", "source_warehouse_id"),
        Index("ix_stock_transfers_tenant_target", "tenant_id", "target_warehouse_id"),
        Index("ix_stock_transfers_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transfer_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=StockTransferStatus.DRAFT.value,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outbound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outbound_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_by: Mapped[int | None] = mapped_column(
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

    source_warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="StockTransfer.source_warehouse_id == Warehouse.id",
        foreign_keys="StockTransfer.source_warehouse_id",
        viewonly=True,
    )
    target_warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="StockTransfer.target_warehouse_id == Warehouse.id",
        foreign_keys="StockTransfer.target_warehouse_id",
        viewonly=True,
    )
    items: Mapped[list[StockTransferItem]] = relationship(
        "StockTransferItem",
        back_populates="stock_transfer",
        cascade="all, delete-orphan",
    )


class StockTransferItem(TimestampMixin, TenantMixin, Base):
    """调拨明细。第一版整条一次调出；收货数量默认等于已调出数量。"""

    __tablename__ = "stock_transfer_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_st_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "stock_transfer_id",
            "sku_id",
            name="uq_st_items_transfer_sku",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "stock_transfer_id"],
            ["stock_transfers.tenant_id", "stock_transfers.id"],
            name="fk_st_items_transfer",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_st_items_sku",
        ),
        CheckConstraint("quantity > 0", name="ck_st_items_qty_positive"),
        CheckConstraint("outbound_quantity >= 0", name="ck_st_items_outbound_nonneg"),
        CheckConstraint("received_quantity >= 0", name="ck_st_items_received_nonneg"),
        CheckConstraint(
            "outbound_quantity <= quantity",
            name="ck_st_items_outbound_lte_qty",
        ),
        CheckConstraint(
            "received_quantity <= outbound_quantity",
            name="ck_st_items_received_lte_outbound",
        ),
        Index("ix_st_items_tenant_transfer", "tenant_id", "stock_transfer_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_transfer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    outbound_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    received_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    stock_transfer: Mapped[StockTransfer] = relationship(back_populates="items")
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="StockTransferItem.sku_id == ProductSku.id",
        foreign_keys="StockTransferItem.sku_id",
        viewonly=True,
    )
