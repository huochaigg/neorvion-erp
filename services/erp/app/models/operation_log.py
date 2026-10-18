"""应用层操作审计。记录哪个用户通过系统执行了什么动作，不等于 binlog。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"
    __table_args__ = (
        Index("ix_operation_logs_tenant_occurred", "tenant_id", "occurred_at"),
        Index(
            "ix_operation_logs_tenant_operator_occurred",
            "tenant_id",
            "operator_user_id",
            "occurred_at",
        ),
        Index(
            "ix_operation_logs_tenant_resource",
            "tenant_id",
            "resource_type",
            "resource_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    operator_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="执行操作的用户 id，系统任务可为空",
    )
    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="稳定动作编码，例如 CONFIRM / APPROVE，不是自然语言描述",
    )
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    request_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="本次 HTTP 请求标识，用于把前端报错、后端日志和操作日志串起来",
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="SUCCESS 或 FAILED",
    )
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="必要上下文快照，禁止保存 password / Authorization / token",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
