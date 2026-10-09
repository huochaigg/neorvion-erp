"""物流商基础资料。V9 不调用真实承运商 API，只作为物流单上的档案。"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class CarrierStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class CarrierType(StrEnum):
    DOMESTIC_EXPRESS = "DOMESTIC_EXPRESS"
    INTERNATIONAL_EXPRESS = "INTERNATIONAL_EXPRESS"
    FREIGHT_FORWARDER = "FREIGHT_FORWARDER"
    PLATFORM_LOGISTICS = "PLATFORM_LOGISTICS"
    OTHER = "OTHER"


class Carrier(TimestampMixin, TenantMixin, Base):
    """租户物流商。code 在同一企业内唯一；创建后默认只读。"""

    __tablename__ = "carriers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_carriers_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_carriers_tenant_code"),
        Index("ix_carriers_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 创建时先空，flush 拿到 id 后再写 CAR{id:010d}。
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    carrier_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=CarrierType.OTHER.value,
    )
    contact_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=CarrierStatus.ACTIVE.value,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
