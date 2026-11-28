"""Chat run lease, interrupt statuses, and event sequence.

Revision ID: 20261128_0018
Revises: 20261123_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261128_0018"
down_revision: str | None = "20261123_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_copilot_messages_status", "copilot_messages", type_="check")
    op.create_check_constraint(
        "ck_copilot_messages_status",
        "copilot_messages",
        "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED', 'TIMED_OUT')",
    )
    op.drop_constraint("ck_copilot_agent_run_status", "copilot_agent_runs", type_="check")
    op.create_check_constraint(
        "ck_copilot_agent_run_status",
        "copilot_agent_runs",
        "status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','DEGRADED','INTERRUPTED','TIMED_OUT')",
    )
    op.add_column("copilot_agent_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column("copilot_agent_runs", sa.Column("last_progress_at", sa.DateTime(timezone=True)))
    op.add_column("copilot_agent_runs", sa.Column("lease_until", sa.DateTime(timezone=True)))
    op.add_column("copilot_agent_runs", sa.Column("worker_instance_id", sa.String(length=64)))
    op.add_column(
        "copilot_agent_runs",
        sa.Column("execution_attempt", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "copilot_agent_runs",
        sa.Column("event_seq", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("copilot_agent_runs", sa.Column("interrupt_reason", sa.String(length=64)))
    op.create_index(
        "ix_copilot_agent_runs_running_lease",
        "copilot_agent_runs",
        ["status", "lease_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_copilot_agent_runs_running_lease", table_name="copilot_agent_runs")
    op.drop_column("copilot_agent_runs", "interrupt_reason")
    op.drop_column("copilot_agent_runs", "event_seq")
    op.drop_column("copilot_agent_runs", "execution_attempt")
    op.drop_column("copilot_agent_runs", "worker_instance_id")
    op.drop_column("copilot_agent_runs", "lease_until")
    op.drop_column("copilot_agent_runs", "last_progress_at")
    op.drop_column("copilot_agent_runs", "heartbeat_at")
    op.drop_constraint("ck_copilot_agent_run_status", "copilot_agent_runs", type_="check")
    op.create_check_constraint(
        "ck_copilot_agent_run_status",
        "copilot_agent_runs",
        "status IN ('RUNNING','SUCCEEDED','FAILED','CANCELLED','DEGRADED')",
    )
    op.drop_constraint("ck_copilot_messages_status", "copilot_messages", type_="check")
    op.create_check_constraint(
        "ck_copilot_messages_status",
        "copilot_messages",
        "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
    )
