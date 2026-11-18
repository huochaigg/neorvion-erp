"""persist Agent Skill file snapshots and Chat associations

Revision ID: 20261113_0014
Revises: 20261029_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261113_0014"
down_revision: str | None = "20261029_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_skill_version_tenant", "copilot_skill_versions", ["tenant_id", "id"]
    )
    op.add_column(
        "copilot_skill_versions",
        sa.Column("source_format", sa.String(24), server_default="JSON_TEMPLATE", nullable=False),
    )
    op.add_column(
        "copilot_skill_versions",
        sa.Column(
            "source_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    op.add_column(
        "copilot_skill_versions",
        sa.Column("resources", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column("copilot_skill_runs", sa.Column("message_id", sa.BigInteger(), nullable=True))
    op.add_column("copilot_skill_runs", sa.Column("selection_method", sa.String(32), nullable=True))
    op.create_foreign_key(
        "fk_skill_run_message",
        "copilot_skill_runs",
        "copilot_messages",
        ["tenant_id", "message_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_skill_run_message", "copilot_skill_runs", ["tenant_id", "message_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_skill_run_message", table_name="copilot_skill_runs")
    op.drop_constraint("fk_skill_run_message", "copilot_skill_runs", type_="foreignkey")
    op.drop_column("copilot_skill_runs", "selection_method")
    op.drop_column("copilot_skill_runs", "message_id")
    op.drop_column("copilot_skill_versions", "resources")
    op.drop_column("copilot_skill_versions", "source_metadata")
    op.drop_column("copilot_skill_versions", "source_format")
    op.drop_constraint("uq_skill_version_tenant", "copilot_skill_versions", type_="unique")
