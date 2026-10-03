"""仓库主数据。后续库存是 Tenant + Warehouse + SKU，本表不存数量。"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, Index, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class WarehouseType(StrEnum):
    DOMESTIC = "DOMESTIC"
    OVERSEAS = "OVERSEAS"
    FBA = "FBA"
    THIRD_PARTY = "THIRD_PARTY"
    OTHER = "OTHER"


class WarehouseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class Warehouse(TimestampMixin, TenantMixin, Base):
    """租户仓库。code 在同一企业内唯一；is_default 由 Service 保证每租户最多一个。"""

    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_warehouses_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
        Index("ix_warehouses_tenant_status", "tenant_id", "status"),
        Index("ix_warehouses_tenant_type", "tenant_id", "type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 创建时先空，flush 拿到 id 后再写 WH{id:010d}；提交前必须非空。
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=WarehouseType.DOMESTIC.value,
    )
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=false(),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=WarehouseStatus.ACTIVE.value,
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
