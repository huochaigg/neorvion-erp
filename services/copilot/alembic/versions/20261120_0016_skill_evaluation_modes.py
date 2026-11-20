"""V14.3 distinguish replay, selector-live and end-to-end evaluation.

Revision ID: 20261120_0016
Revises: 20261119_0015
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261120_0016"
down_revision: str | None = "20261119_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_agent_eval_execution_kind",
        "copilot_agent_evaluation_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_eval_execution_kind",
        "copilot_agent_evaluation_runs",
        "execution_kind IN ('REPLAY','LIVE','SELECTOR_LIVE','END_TO_END')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE copilot_agent_evaluation_runs "
        "SET execution_kind = 'LIVE' "
        "WHERE execution_kind IN ('SELECTOR_LIVE','END_TO_END')"
    )
    op.drop_constraint(
        "ck_agent_eval_execution_kind",
        "copilot_agent_evaluation_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_eval_execution_kind",
        "copilot_agent_evaluation_runs",
        "execution_kind IN ('REPLAY','LIVE')",
    )
