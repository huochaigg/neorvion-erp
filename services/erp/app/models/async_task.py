"""异步任务与任务日志。状态以 MySQL 为准，Redis 只负责投递 task_id。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin


class AsyncTask(TimestampMixin, Base):
    __tablename__ = "async_tasks"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_async_tasks_task_id"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_async_tasks_progress"),
        Index("ix_async_tasks_tenant_created", "tenant_id", "created_at"),
        Index("ix_async_tasks_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="异步任务对外唯一标识，与数据库自增 id 分离，供队列、日志和前端查询使用",
    )
    task_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="任务类型，第一版以 REPORT_EXPORT 为主",
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PENDING")
    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="异步任务当前进度百分比，范围 0-100",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="成功结果摘要，例如导出文件名和行数，不含服务器任意路径",
    )
    error_message: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="可展示的简要失败原因，不包含 traceback 和密钥",
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("3"),
        comment="允许人工重试的最大次数",
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="用于识别同一业务任务的幂等键，避免重复执行产生重复业务副作用",
    )


class AsyncTaskLog(Base):
    __tablename__ = "async_task_logs"
    __table_args__ = (Index("ix_async_task_logs_task_created", "task_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="对应 AsyncTask.task_id，不是数据库自增 id",
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False, server_default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
