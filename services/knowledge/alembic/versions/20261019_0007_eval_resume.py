"""评测断点续跑：PAUSED、租约、阶段 checkpoint、Run 预算。

Revision ID: 20261019_0007
Revises: 20261014_0006
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261019_0007"
down_revision: str | None = "20261014_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("pause_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("evaluation_runs", sa.Column("interrupt_reason", sa.String(length=32), nullable=True))
    op.add_column("evaluation_runs", sa.Column("current_case_id", sa.BigInteger(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("current_stage", sa.String(length=16), nullable=True))
    op.add_column("evaluation_runs", sa.Column("token_budget", sa.Integer(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("cost_budget_usd", sa.Float(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("lease_owner", sa.String(length=64), nullable=True))
    op.add_column("evaluation_runs", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.drop_index("uq_evaluation_runs_active", table_name="evaluation_runs")
    op.create_index(
        "uq_evaluation_runs_active",
        "evaluation_runs",
        ["tenant_id", "experiment_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING', 'PAUSED')"),
    )

    op.add_column(
        "evaluation_results",
        sa.Column("result_status", sa.String(length=16), nullable=False, server_default="SUCCESS"),
    )
    op.add_column(
        "evaluation_results",
        sa.Column(
            "stages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE evaluation_results
        SET result_status = 'FAILED'
        WHERE error_message IS NOT NULL AND error_message <> ''
        """
    )


def downgrade() -> None:
    op.drop_column("evaluation_results", "stages")
    op.drop_column("evaluation_results", "result_status")
    op.drop_index("uq_evaluation_runs_active", table_name="evaluation_runs")
    op.create_index(
        "uq_evaluation_runs_active",
        "evaluation_runs",
        ["tenant_id", "experiment_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )
    op.drop_column("evaluation_runs", "lease_until")
    op.drop_column("evaluation_runs", "lease_owner")
    op.drop_column("evaluation_runs", "cost_budget_usd")
    op.drop_column("evaluation_runs", "token_budget")
    op.drop_column("evaluation_runs", "current_stage")
    op.drop_column("evaluation_runs", "current_case_id")
    op.drop_column("evaluation_runs", "interrupt_reason")
    op.drop_column("evaluation_runs", "pause_requested")
