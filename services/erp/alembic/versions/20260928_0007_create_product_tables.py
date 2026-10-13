"""V3 商品类目、品牌、SPU、SKU。

Revision ID: 20260928_0007
Revises: 20260928_0006
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260928_0007"
down_revision: str | None = "20260928_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_product_categories_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["product_categories.tenant_id", "product_categories.id"],
            name="fk_product_categories_parent",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_product_categories_tenant_id"),
    )
    op.create_index(
        "ix_product_categories_tenant_id",
        "product_categories",
        ["tenant_id"],
    )
    op.create_index(
        "ix_product_categories_tenant_parent",
        "product_categories",
        ["tenant_id", "parent_id"],
    )

    op.create_table(
        "brands",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("logo_url", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_brands_tenant"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_brands_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_brands_tenant_code"),
    )
    op.create_index("ix_brands_tenant_id", "brands", ["tenant_id"])

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("brand_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_products_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["product_categories.tenant_id", "product_categories.id"],
            name="fk_products_category",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_products_brand",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_products_tenant_code"),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"])
    op.create_index("ix_products_tenant_category", "products", ["tenant_id", "category_id"])
    op.create_index("ix_products_tenant_brand", "products", ["tenant_id", "brand_id"])
    op.create_index("ix_products_tenant_status", "products", ["tenant_id", "status"])

    op.create_table(
        "product_skus",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("sku_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("spec_values", mysql.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_product_skus_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_skus_product",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_product_skus_tenant_id"),
        sa.UniqueConstraint("tenant_id", "sku_code", name="uq_product_skus_tenant_code"),
    )
    op.create_index("ix_product_skus_tenant_id", "product_skus", ["tenant_id"])
    op.create_index(
        "ix_product_skus_tenant_product",
        "product_skus",
        ["tenant_id", "product_id"],
    )


def downgrade() -> None:
    op.drop_table("product_skus")
    op.drop_table("products")
    op.drop_table("brands")
    op.drop_table("product_categories")
