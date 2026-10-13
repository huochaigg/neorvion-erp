from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.product import Brand, CatalogStatus, Product, ProductCategory, ProductSku
from app.repositories.base import BaseRepository


class ProductCategoryRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def list_all(self) -> list[ProductCategory]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(ProductCategory)
            .where(ProductCategory.tenant_id == tenant_id)
            .order_by(
                ProductCategory.level.asc(),
                ProductCategory.sort.asc(),
                ProductCategory.id.asc(),
            )
        )
        return list(self.session.scalars(stmt).all())

    def get_in_tenant(self, category_id: int) -> ProductCategory | None:
        tenant_id = self.ensure_tenant()
        stmt = select(ProductCategory).where(
            ProductCategory.tenant_id == tenant_id,
            ProductCategory.id == category_id,
        )
        return self.session.scalars(stmt).first()

    def count_children(self, category_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(ProductCategory.id)).where(
            ProductCategory.tenant_id == tenant_id,
            ProductCategory.parent_id == category_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def find_sibling_name(
        self,
        *,
        parent_id: int | None,
        name: str,
        exclude_id: int | None = None,
    ) -> ProductCategory | None:
        tenant_id = self.ensure_tenant()
        stmt = select(ProductCategory).where(
            ProductCategory.tenant_id == tenant_id,
            ProductCategory.name == name,
        )
        if parent_id is None:
            stmt = stmt.where(ProductCategory.parent_id.is_(None))
        else:
            stmt = stmt.where(ProductCategory.parent_id == parent_id)
        if exclude_id is not None:
            stmt = stmt.where(ProductCategory.id != exclude_id)
        return self.session.scalars(stmt).first()

    def add(self, category: ProductCategory) -> ProductCategory:
        self.session.add(category)
        return category

    def delete(self, category: ProductCategory) -> None:
        self.session.delete(category)


class BrandRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def list_page(
        self,
        *,
        q: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Brand], int]:
        tenant_id = self.ensure_tenant()
        filters = [Brand.tenant_id == tenant_id]
        if status:
            filters.append(Brand.status == status)
        if q:
            pattern = f"%{q}%"
            filters.append(Brand.name.like(pattern) | Brand.code.like(pattern))
        count_stmt = select(func.count(Brand.id)).where(*filters)
        total = int(self.session.scalar(count_stmt) or 0)
        stmt = (
            select(Brand)
            .where(*filters)
            .order_by(Brand.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.session.scalars(stmt).all()), total

    def list_all_active(self) -> list[Brand]:
        """商品表单下拉只用启用品牌。scalars() 直接得到 Brand 行，不用 row[0]。"""
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Brand)
            .where(
                Brand.tenant_id == tenant_id,
                Brand.status == CatalogStatus.ACTIVE.value,
            )
            .order_by(Brand.name.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get_in_tenant(self, brand_id: int) -> Brand | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Brand).where(Brand.tenant_id == tenant_id, Brand.id == brand_id)
        return self.session.scalars(stmt).first()

    def get_by_code(self, code: str) -> Brand | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Brand).where(Brand.tenant_id == tenant_id, Brand.code == code)
        return self.session.scalars(stmt).first()

    def add(self, brand: Brand) -> Brand:
        self.session.add(brand)
        return brand

    def delete(self, brand: Brand) -> None:
        self.session.delete(brand)


class ProductRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def _detail_options(self):
        return (
            selectinload(Product.category),
            selectinload(Product.brand),
            selectinload(Product.skus),
        )

    def get_in_tenant(self, product_id: int) -> Product | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(Product)
            .options(*self._detail_options())
            .where(Product.tenant_id == tenant_id, Product.id == product_id)
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(stmt).first()

    def get_by_code(self, code: str) -> Product | None:
        tenant_id = self.ensure_tenant()
        stmt = select(Product).where(Product.tenant_id == tenant_id, Product.code == code)
        return self.session.scalars(stmt).first()

    def count_by_category(self, category_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(Product.id)).where(
            Product.tenant_id == tenant_id,
            Product.category_id == category_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def count_by_brand(self, brand_id: int) -> int:
        tenant_id = self.ensure_tenant()
        stmt = select(func.count(Product.id)).where(
            Product.tenant_id == tenant_id,
            Product.brand_id == brand_id,
        )
        return int(self.session.scalar(stmt) or 0)

    def list_page(
        self,
        *,
        q: str | None,
        sku_code: str | None,
        category_id: int | None,
        brand_id: int | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[Product, int]], int]:
        """分页查 SPU，SKU 数量用聚合，避免把全部 SKU 拉进内存再 len()。

        selectinload(category/brand)：列表只要名称，额外两次 IN 查询，不是每个商品一条。
        execute().all() 得到 (Product, sku_count) 元组；scalars() 只能取第一列，这里不能用。
        """
        tenant_id = self.ensure_tenant()
        count_sq = (
            select(ProductSku.product_id, func.count(ProductSku.id).label("sku_count"))
            .where(ProductSku.tenant_id == tenant_id)
            .group_by(ProductSku.product_id)
            .subquery()
        )
        filters = [Product.tenant_id == tenant_id]
        if status:
            filters.append(Product.status == status)
        if category_id:
            filters.append(Product.category_id == category_id)
        if brand_id:
            filters.append(Product.brand_id == brand_id)
        if q:
            pattern = f"%{q}%"
            filters.append((Product.name.like(pattern)) | (Product.code.like(pattern)))
        if sku_code:
            sku_ids = (
                select(ProductSku.product_id)
                .where(
                    ProductSku.tenant_id == tenant_id,
                    ProductSku.sku_code.like(f"%{sku_code}%"),
                )
                .distinct()
            )
            filters.append(Product.id.in_(sku_ids))

        count_stmt = select(func.count(Product.id)).where(*filters)
        total = int(self.session.scalar(count_stmt) or 0)
        stmt = (
            select(Product, func.coalesce(count_sq.c.sku_count, 0))
            .options(selectinload(Product.category), selectinload(Product.brand))
            .outerjoin(count_sq, count_sq.c.product_id == Product.id)
            .where(*filters)
            .order_by(Product.created_at.desc(), Product.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(self.session.execute(stmt).all())
        return [(row[0], int(row[1])) for row in rows], total

    def add(self, product: Product) -> Product:
        self.session.add(product)
        return product

    def delete(self, product: Product) -> None:
        self.session.delete(product)


class ProductSkuRepository(BaseRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    def get_by_id_in_tenant(self, sku_id: int) -> ProductSku | None:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(ProductSku)
            .options(selectinload(ProductSku.product))
            .where(ProductSku.tenant_id == tenant_id, ProductSku.id == sku_id)
        )
        return self.session.scalars(stmt).first()

    def get_in_tenant(self, *, product_id: int, sku_id: int) -> ProductSku | None:
        tenant_id = self.ensure_tenant()
        stmt = select(ProductSku).where(
            ProductSku.tenant_id == tenant_id,
            ProductSku.product_id == product_id,
            ProductSku.id == sku_id,
        )
        return self.session.scalars(stmt).first()

    def get_by_code(self, sku_code: str) -> ProductSku | None:
        tenant_id = self.ensure_tenant()
        stmt = select(ProductSku).where(
            ProductSku.tenant_id == tenant_id,
            ProductSku.sku_code == sku_code,
        )
        return self.session.scalars(stmt).first()

    def list_for_product(self, product_id: int) -> list[ProductSku]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(ProductSku)
            .where(
                ProductSku.tenant_id == tenant_id,
                ProductSku.product_id == product_id,
            )
            .order_by(ProductSku.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def add(self, sku: ProductSku) -> ProductSku:
        self.session.add(sku)
        return sku

    def delete(self, sku: ProductSku) -> None:
        self.session.delete(sku)

    def delete_for_product(self, product_id: int) -> None:
        tenant_id = self.ensure_tenant()
        rows = self.list_for_product(product_id)
        for row in rows:
            if row.tenant_id == tenant_id:
                self.session.delete(row)
