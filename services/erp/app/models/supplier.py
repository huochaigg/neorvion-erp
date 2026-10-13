"""供应商主数据。采购单引用供应商；禁用后不能新建采购单，历史单据保留。"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class SupplierStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class Supplier(TimestampMixin, TenantMixin, Base):
    """租户供应商。code 在同一企业内唯一；创建后默认只读。"""

    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_suppliers_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
        Index("ix_suppliers_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 创建时先空，flush 拿到 id 后再写 SUP{id:010d}。
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=SupplierStatus.ACTIVE.value,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
