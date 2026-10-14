"""为已落地的 V5 表补 created_at/updated_at 数据库默认值。

Revision ID: 20261014_0006
Revises: 20261014_0005
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_0006"
down_revision: str | None = "20261014_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "document_revisions",
    "knowledge_base_grants",
    "knowledge_api_keys",
    "knowledge_audit_logs",
)


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "created_at", server_default=sa.func.now())
        op.alter_column(table, "updated_at", server_default=sa.func.now())


def downgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "created_at", server_default=None)
        op.alter_column(table, "updated_at", server_default=None)
