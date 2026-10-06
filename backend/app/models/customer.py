"""客户主数据。销售订单引用客户；禁用后不能新建订单，历史单据保留。"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class CustomerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class Customer(TimestampMixin, TenantMixin, Base):
    """租户客户。code 在同一企业内唯一；创建后只读。

    订单不实时读这里的地址。下单时把收货信息抄到 SalesOrder，避免客户以后改地址改写历史订单。
    """

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_customers_tenant_code"),
        Index("ix_customers_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 创建时先空，flush 拿到 id 后再写 CUS{id:010d}。不用 MAX(code)+1。
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=CustomerStatus.ACTIVE.value,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
