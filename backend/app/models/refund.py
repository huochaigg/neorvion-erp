"""退款记录。一次售后可以有多次尝试：失败后新建一条，不能覆盖失败历史。"""

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
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.models.after_sale import AfterSaleOrder

REFUND_REFERENCE = "REFUND"


class RefundRecordStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RefundRecord(TimestampMixin, TenantMixin, Base):
    """一次具体退款动作。V11 只做 ERP 内人工确认，不接支付宝/微信/Stripe。"""

    __tablename__ = "refund_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_refund_records_tenant_id"),
        UniqueConstraint("tenant_id", "refund_no", name="uq_refund_records_tenant_no"),
        ForeignKeyConstraint(
            ["tenant_id", "after_sale_order_id"],
            ["after_sale_orders.tenant_id", "after_sale_orders.id"],
            name="fk_refund_records_after_sale",
        ),
        CheckConstraint("amount >= 0", name="ck_refund_records_amount_nonneg"),
        Index("ix_refund_records_tenant_after_sale", "tenant_id", "after_sale_order_id"),
        Index("ix_refund_records_tenant_status", "tenant_id", "status"),
        Index("ix_refund_records_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    after_sale_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refund_no: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="RF + 年份 + 6 位 id，租户内唯一",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="本次退款金额，不能超过售后剩余可退金额",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=RefundRecordStatus.PENDING.value,
    )
    external_reference_no: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="外部渠道退款流水号，留给以后对接支付平台",
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    after_sale_order: Mapped[AfterSaleOrder] = relationship(
        primaryjoin="RefundRecord.after_sale_order_id == AfterSaleOrder.id",
        foreign_keys="RefundRecord.after_sale_order_id",
        viewonly=True,
    )
