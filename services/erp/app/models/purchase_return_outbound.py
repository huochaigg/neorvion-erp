"""采购退货出库单。计划单是 PurchaseReturn，本表记录每次实际从仓库退走多少。"""

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
from app.models.purchase_return import PurchaseReturn, PurchaseReturnItem
from app.models.warehouse import Warehouse

PURCHASE_RETURN_OUTBOUND_REFERENCE = "PURCHASE_RETURN_OUTBOUND"


class PurchaseReturnOutboundStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class PurchaseReturnOutbound(TimestampMixin, TenantMixin, Base):
    """一次实际退货出库。草稿不改库存；确认后扣减 available 并写流水。"""

    __tablename__ = "purchase_return_outbounds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_pr_outbounds_tenant_id"),
        UniqueConstraint("tenant_id", "outbound_no", name="uq_pr_outbounds_tenant_no"),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_return_id"],
            ["purchase_returns.tenant_id", "purchase_returns.id"],
            name="fk_pr_outbounds_return",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_pr_outbounds_warehouse",
        ),
        Index("ix_pr_outbounds_tenant_return", "tenant_id", "purchase_return_id"),
        Index("ix_pr_outbounds_tenant_status", "tenant_id", "status"),
        Index("ix_pr_outbounds_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    outbound_no: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="PRO + 年份 + 6 位 id，租户内唯一，不用 MAX+1",
    )
    purchase_return_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="本次出库仓库快照，必须与采购退货单 warehouse_id 一致",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=PurchaseReturnOutboundStatus.DRAFT.value,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
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

    purchase_return: Mapped[PurchaseReturn] = relationship(
        primaryjoin="PurchaseReturnOutbound.purchase_return_id == PurchaseReturn.id",
        foreign_keys="PurchaseReturnOutbound.purchase_return_id",
        viewonly=True,
    )
    warehouse: Mapped[Warehouse] = relationship(
        primaryjoin="PurchaseReturnOutbound.warehouse_id == Warehouse.id",
        foreign_keys="PurchaseReturnOutbound.warehouse_id",
        viewonly=True,
    )
    items: Mapped[list[PurchaseReturnOutboundItem]] = relationship(
        "PurchaseReturnOutboundItem",
        back_populates="outbound",
        cascade="all, delete-orphan",
    )


class PurchaseReturnOutboundItem(TimestampMixin, TenantMixin, Base):
    """一次出库动作里某个退货明细实际退走的数量。"""

    __tablename__ = "purchase_return_outbound_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_pr_outbound_items_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "purchase_return_outbound_id",
            "purchase_return_item_id",
            name="uq_pr_ob_items_outbound_return_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_return_outbound_id"],
            ["purchase_return_outbounds.tenant_id", "purchase_return_outbounds.id"],
            name="fk_pr_ob_items_outbound",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_return_item_id"],
            ["purchase_return_items.tenant_id", "purchase_return_items.id"],
            name="fk_pr_ob_items_return_item",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "sku_id"],
            ["product_skus.tenant_id", "product_skus.id"],
            name="fk_pr_ob_items_sku",
        ),
        CheckConstraint("quantity > 0", name="ck_pr_ob_items_qty_pos"),
        Index("ix_pr_ob_items_tenant_outbound", "tenant_id", "purchase_return_outbound_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_return_outbound_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchase_return_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sku_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="本次实际退货出库数量，不是累计已退",
    )

    outbound: Mapped[PurchaseReturnOutbound] = relationship(back_populates="items")
    purchase_return_item: Mapped[PurchaseReturnItem] = relationship(
        primaryjoin="PurchaseReturnOutboundItem.purchase_return_item_id == PurchaseReturnItem.id",
        foreign_keys="PurchaseReturnOutboundItem.purchase_return_item_id",
        viewonly=True,
    )
    sku: Mapped[ProductSku] = relationship(
        primaryjoin="PurchaseReturnOutboundItem.sku_id == ProductSku.id",
        foreign_keys="PurchaseReturnOutboundItem.sku_id",
        viewonly=True,
    )
