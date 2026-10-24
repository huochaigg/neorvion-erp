"""add V9 judge and human review fields

Revision ID: 20261025_0009
Revises: 20261025_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261025_0009"
down_revision: str | None = "20261025_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("copilot_agent_evaluation_case_runs", sa.Column("judge_model", sa.String(128)))
    op.add_column(
        "copilot_agent_evaluation_case_runs",
        sa.Column("judge_prompt_version", sa.String(64)),
    )
    op.add_column(
        "copilot_agent_evaluation_case_runs",
        sa.Column("judge_feedback", postgresql.JSONB()),
    )
    op.add_column(
        "copilot_agent_evaluation_case_runs",
        sa.Column("judge_confidence", sa.Numeric(6, 5)),
    )
    op.add_column(
        "copilot_agent_evaluation_case_runs",
        sa.Column("human_override", postgresql.JSONB()),
    )


def downgrade() -> None:
    op.drop_column("copilot_agent_evaluation_case_runs", "human_override")
    op.drop_column("copilot_agent_evaluation_case_runs", "judge_confidence")
    op.drop_column("copilot_agent_evaluation_case_runs", "judge_feedback")
    op.drop_column("copilot_agent_evaluation_case_runs", "judge_prompt_version")
    op.drop_column("copilot_agent_evaluation_case_runs", "judge_model")
