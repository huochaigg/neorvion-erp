"""add V10 proactive insights

Revision ID: 7f803d545046
Revises: 20261025_0009
"""

from collections.abc import Sequence

from alembic import op
from app.models.insight import (
    BusinessInsight,
    InsightDetectionRun,
    InsightEvent,
    InsightNotification,
    InsightRule,
    InsightRuleRevision,
)

revision: str = "7f803d545046"
down_revision: str | None = "20261025_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    for model in (
        InsightRule,
        InsightRuleRevision,
        InsightDetectionRun,
        BusinessInsight,
        InsightEvent,
        InsightNotification,
    ):
        model.__table__.create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    for model in (
        InsightNotification,
        InsightEvent,
        BusinessInsight,
        InsightDetectionRun,
        InsightRuleRevision,
        InsightRule,
    ):
        model.__table__.drop(bind=bind)
