"""商品类目、品牌、SPU、SKU。

库存、采购、订单后续只关联 SKU，不要给 SPU 建库存。
类目 / 品牌 / 商品都带 tenant_id；复合外键保证不能把 A 企业的类目挂到 B 企业的商品上。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class CatalogStatus(StrEnum):
    # 类目状态：有效、禁用。
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class ProductStatus(StrEnum):
    # 商品状态：草稿、上架、下架。
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class SkuStatus(StrEnum):
    # SKU 状态：有效、禁用。
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ProductCategory(TimestampMixin, TenantMixin, Base):
    """租户内商品类目。parent_id 自关联，最多三级。"""

    __tablename__ = "product_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_product_categories_tenant_id"),
        # 父类目必须同租户。parent_id 为空时复合外键不生效，根节点合法。
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["product_categories.tenant_id", "product_categories.id"],
            name="fk_product_categories_parent",
        ),
        Index("ix_product_categories_tenant_parent", "tenant_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=CatalogStatus.ACTIVE.value,
    )


class Brand(TimestampMixin, TenantMixin, Base):
    """租户自有品牌。code 在同一企业内唯一，不同企业可以都叫 NIKE。"""

    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_brands_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_brands_tenant_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=CatalogStatus.ACTIVE.value,
    )


class Product(TimestampMixin, TenantMixin, Base):
    """SPU：一类商品，例如 iPhone 17。真正可库存的是下面的 SKU。"""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_products_tenant_code"),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["product_categories.tenant_id", "product_categories.id"],
            name="fk_products_category",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_products_brand",
        ),
        Index("ix_products_tenant_category", "tenant_id", "category_id"),
        Index("ix_products_tenant_brand", "tenant_id", "brand_id"),
        Index("ix_products_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    brand_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 创建时可空：flush 拿到自增 id 后再写成 PD{id:010d}。提交前 Service 必须填好。
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=ProductStatus.DRAFT.value,
    )

    category: Mapped[ProductCategory] = relationship(
        primaryjoin="Product.category_id == ProductCategory.id",
        foreign_keys="Product.category_id",
        viewonly=True,
    )
    brand: Mapped[Brand | None] = relationship(
        primaryjoin="Product.brand_id == Brand.id",
        foreign_keys="Product.brand_id",
        viewonly=True,
    )
    skus: Mapped[list[ProductSku]] = relationship(
        primaryjoin="Product.id == ProductSku.product_id",
        foreign_keys="ProductSku.product_id",
        viewonly=True,
    )


class ProductSku(TimestampMixin, TenantMixin, Base):
    """SKU：可销售最小单位。后续库存/采购/订单必须挂这一行，不能挂 SPU。"""

    __tablename__ = "product_skus"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_product_skus_tenant_id"),
        UniqueConstraint("tenant_id", "sku_code", name="uq_product_skus_tenant_code"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_skus_product",
        ),
        Index("ix_product_skus_tenant_product", "tenant_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 与商品 code 相同：允许 INSERT 时为空，flush 后写成 SKU{id:010d}。
    sku_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 简单键值规格，例如 {"color": "黑色"}。V3 不用 EAV；JSON 便于读写，后续订单只认 SKU 行。
    spec_values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=SkuStatus.ACTIVE.value,
    )

    product: Mapped[Product] = relationship(
        primaryjoin="ProductSku.product_id == Product.id",
        foreign_keys="ProductSku.product_id",
        viewonly=True,
    )
