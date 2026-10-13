"""V3 商品编码允许创建时为空，flush 拿到自增 id 后再写入。

Revision ID: 20261003_0008
Revises: 20260928_0007
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_0008"
down_revision: str | None = "20260928_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 创建时先 INSERT 空编码，flush 后用自增 id 生成 PD/SKU 编号。
    # UNIQUE(tenant_id, code) 对 NULL 允许多行，提交前 Service 必须填好，不能留下空编码。
    op.alter_column(
        "products",
        "code",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.alter_column(
        "product_skus",
        "sku_code",
        existing_type=sa.String(length=64),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "product_skus",
        "sku_code",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "products",
        "code",
        existing_type=sa.String(length=64),
        nullable=False,
    )
