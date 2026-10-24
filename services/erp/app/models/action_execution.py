from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin


class ErpActionExecutionReceipt(TenantMixin, Base):
    """Copilot 写入的 ERP 侧最终幂等凭据，与业务单据在同一 MySQL 事务提交。"""

    __tablename__ = "erp_action_execution_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "execution_key", name="uq_erp_action_receipt_key"),
        CheckConstraint("status IN ('EXECUTING','SUCCEEDED')", name="ck_erp_action_receipt_status"),
        Index("ix_erp_action_receipt_resource", "tenant_id", "resource_type", "resource_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_revision: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[int | None] = mapped_column(BigInteger)
    resource_no: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
