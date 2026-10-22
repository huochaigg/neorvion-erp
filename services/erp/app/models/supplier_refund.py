"""供应商退款记录。一次采购退货可以有多次尝试：失败后新建一条，不能覆盖失败历史。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.models.purchase_return import PurchaseReturn

SUPPLIER_REFUND_REFERENCE = "SUPPLIER_REFUND"


class SupplierRefundRecordStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class SupplierRefundRecord(TimestampMixin, TenantMixin, Base):
    """一次具体供应商退款动作。V12 只做 ERP 内人工确认，不接银行或应付结算。"""

    __tablename__ = "supplier_refund_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_supplier_refunds_tenant_id"),
        UniqueConstraint("tenant_id", "refund_no", name="uq_supplier_refunds_tenant_no"),
        ForeignKeyConstraint(
            ["tenant_id", "purchase_return_id"],
            ["purchase_returns.tenant_id", "purchase_returns.id"],
            name="fk_supplier_refunds_return",
        ),
        CheckConstraint("amount >= 0", name="ck_supplier_refunds_amount_nonneg"),
        Index("ix_supplier_refunds_tenant_return", "tenant_id", "purchase_return_id"),
        Index("ix_supplier_refunds_tenant_status", "tenant_id", "status"),
        Index("ix_supplier_refunds_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    purchase_return_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refund_no: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="SRF + 年份 + 6 位 id，租户内唯一",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="本次供应商退款金额，不能超过批准剩余可退金额",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=SupplierRefundRecordStatus.PENDING.value,
    )
    external_reference_no: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="外部银行或供应商付款流水号，本版仅人工记录",
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="确认供应商退款到账的时间，确认成功时写入",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    purchase_return: Mapped[PurchaseReturn] = relationship(
        primaryjoin=(
            "and_(SupplierRefundRecord.tenant_id == PurchaseReturn.tenant_id, "
            "SupplierRefundRecord.purchase_return_id == PurchaseReturn.id)"
        ),
        foreign_keys="SupplierRefundRecord.purchase_return_id",
        viewonly=True,
    )
