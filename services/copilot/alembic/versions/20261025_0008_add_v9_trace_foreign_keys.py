"""add V9 trace foreign keys

Revision ID: 20261025_0008
Revises: 20261025_0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261025_0008"
down_revision: str | None = "20261025_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_model_call_agent_run",
        "copilot_model_calls",
        "copilot_agent_runs",
        ["tenant_id", "agent_run_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_agent_eval_case_run_agent_trace",
        "copilot_agent_evaluation_case_runs",
        "copilot_agent_runs",
        ["tenant_id", "agent_run_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_agent_eval_comparison_baseline",
        "copilot_agent_evaluation_comparisons",
        "copilot_agent_evaluation_runs",
        ["tenant_id", "baseline_run_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_agent_eval_comparison_candidate",
        "copilot_agent_evaluation_comparisons",
        "copilot_agent_evaluation_runs",
        ["tenant_id", "candidate_run_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_agent_eval_comparison_candidate",
        "copilot_agent_evaluation_comparisons",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_eval_comparison_baseline",
        "copilot_agent_evaluation_comparisons",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_eval_case_run_agent_trace",
        "copilot_agent_evaluation_case_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_model_call_agent_run", "copilot_model_calls", type_="foreignkey"
    )
