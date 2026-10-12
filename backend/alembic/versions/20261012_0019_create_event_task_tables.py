"""V14 事件中心、操作日志与异步任务表。

Revision ID: 20261012_0019
Revises: 20261011_0018
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_0019"
down_revision: str | None = "20261011_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "event_id",
            sa.String(length=64),
            nullable=False,
            comment="事件全局唯一标识，用于异步消费去重和跨系统追踪",
        ),
        sa.Column(
            "event_type",
            sa.String(length=64),
            nullable=False,
            comment="稳定事件类型，例如 SALES_ORDER_CONFIRMED",
        ),
        sa.Column(
            "event_source",
            sa.String(length=32),
            server_default="ERP",
            nullable=False,
            comment="事件由哪个子系统产生：ERP / SYSTEM / TASK",
        ),
        sa.Column(
            "aggregate_type",
            sa.String(length=32),
            nullable=False,
            comment="事件所属业务聚合类型，例如 SALES_ORDER、PURCHASE_ORDER、INVENTORY",
        ),
        sa.Column(
            "aggregate_id",
            sa.BigInteger(),
            nullable=True,
            comment="主要业务聚合主键，用于查询某张单据发生过什么",
        ),
        sa.Column(
            "reference_type",
            sa.String(length=32),
            nullable=True,
            comment="补充关联对象类型，语义与库存流水 reference_type 一致",
        ),
        sa.Column(
            "reference_id",
            sa.BigInteger(),
            nullable=True,
            comment="关联业务对象主键，用于从事件详情跳转到原业务单据",
        ),
        sa.Column(
            "severity",
            sa.String(length=16),
            server_default="INFO",
            nullable=False,
            comment="INFO 普通业务；WARNING 库存不足；ERROR 任务失败；CRITICAL 严重异常",
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=True,
            comment="事件必要快照 JSON，禁止包含密码、令牌和密钥",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="扩展追踪信息，例如 request_id、operator_user_id",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
            comment="Outbox 处理状态：PENDING / PROCESSING / PROCESSED / FAILED",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Outbox 消费失败已重试次数，上限 3",
        ),
        sa.Column(
            "last_error",
            sa.String(length=512),
            nullable=True,
            comment="最近一次消费失败的简要原因，不存完整 traceback",
        ),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "next_retry_at",
            sa.DateTime(),
            nullable=True,
            comment="下次允许 Outbox 重试的时间；空表示可立即领取",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_system_events_event_id"),
    )
    op.create_index("ix_system_events_tenant_id", "system_events", ["tenant_id"])
    op.create_index("ix_system_events_tenant_occurred", "system_events", ["tenant_id", "occurred_at"])
    op.create_index(
        "ix_system_events_tenant_type_occurred",
        "system_events",
        ["tenant_id", "event_type", "occurred_at"],
    )
    op.create_index(
        "ix_system_events_tenant_aggregate",
        "system_events",
        ["tenant_id", "aggregate_type", "aggregate_id"],
    )
    op.create_index("ix_system_events_status_created", "system_events", ["status", "created_at"])

    op.create_table(
        "operation_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "operator_user_id",
            sa.BigInteger(),
            nullable=True,
            comment="执行操作的用户 id，系统任务可为空",
        ),
        sa.Column(
            "action",
            sa.String(length=32),
            nullable=False,
            comment="稳定动作编码，例如 CONFIRM / APPROVE，不是自然语言描述",
        ),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=True),
        sa.Column("resource_id", sa.BigInteger(), nullable=True),
        sa.Column("resource_name", sa.String(length=128), nullable=True),
        sa.Column("request_method", sa.String(length=8), nullable=True),
        sa.Column("request_path", sa.String(length=255), nullable=True),
        sa.Column(
            "request_id",
            sa.String(length=64),
            nullable=True,
            comment="本次 HTTP 请求标识，用于把前端报错、后端日志和操作日志串起来",
        ),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=False, comment="SUCCESS 或 FAILED"),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="必要上下文快照，禁止保存 password / Authorization / token",
        ),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operation_logs_tenant_id", "operation_logs", ["tenant_id"])
    op.create_index(
        "ix_operation_logs_tenant_occurred", "operation_logs", ["tenant_id", "occurred_at"]
    )
    op.create_index(
        "ix_operation_logs_tenant_operator_occurred",
        "operation_logs",
        ["tenant_id", "operator_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_operation_logs_tenant_resource",
        "operation_logs",
        ["tenant_id", "resource_type", "resource_id"],
    )

    op.create_table(
        "async_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "task_id",
            sa.String(length=64),
            nullable=False,
            comment="异步任务对外唯一标识，与数据库自增 id 分离，供队列、日志和前端查询使用",
        ),
        sa.Column(
            "task_type",
            sa.String(length=64),
            nullable=False,
            comment="任务类型，第一版以 REPORT_EXPORT 为主",
        ),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column(
            "progress",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="异步任务当前进度百分比，范围 0-100",
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "result",
            sa.JSON(),
            nullable=True,
            comment="成功结果摘要，例如导出文件名和行数，不含服务器任意路径",
        ),
        sa.Column(
            "error_message",
            sa.String(length=512),
            nullable=True,
            comment="可展示的简要失败原因，不包含 traceback 和密钥",
        ),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "max_retries",
            sa.Integer(),
            server_default="3",
            nullable=False,
            comment="允许人工重试的最大次数",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column(
            "idempotency_key",
            sa.String(length=64),
            nullable=True,
            comment="用于识别同一业务任务的幂等键，避免重复执行产生重复业务副作用",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_async_tasks_progress"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_async_tasks_task_id"),
    )
    op.create_index("ix_async_tasks_tenant_id", "async_tasks", ["tenant_id"])
    op.create_index("ix_async_tasks_tenant_created", "async_tasks", ["tenant_id", "created_at"])
    op.create_index(
        "ix_async_tasks_tenant_status_created",
        "async_tasks",
        ["tenant_id", "status", "created_at"],
    )

    op.create_table(
        "async_task_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "task_id",
            sa.String(length=64),
            nullable=False,
            comment="对应 AsyncTask.task_id，不是数据库自增 id",
        ),
        sa.Column("level", sa.String(length=16), server_default="INFO", nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_async_task_logs_tenant_id", "async_task_logs", ["tenant_id"])
    op.create_index("ix_async_task_logs_task_created", "async_task_logs", ["task_id", "created_at"])


def downgrade() -> None:
    op.drop_table("async_task_logs")
    op.drop_table("async_tasks")
    op.drop_table("operation_logs")
    op.drop_table("system_events")
