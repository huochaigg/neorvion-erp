"""SPU / SKU。创建商品必须同一事务写入全部 SKU，失败则整单回滚。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.product import Product, ProductSku, ProductStatus, SkuStatus
from app.repositories.product import (
    BrandRepository,
    ProductCategoryRepository,
    ProductRepository,
    ProductSkuRepository,
)
from app.schemas.product import (
    ProductCreate,
    ProductDetailOut,
    ProductListItem,
    ProductListOut,
    ProductUpdate,
    SkuInput,
    SkuOut,
    SkuUpdate,
)
from app.services.authorization import AuthorizationService

_PRODUCT_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,63}$")
_UNAVAILABLE = "资源不存在或不可访问"


class ProductService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.products = ProductRepository(session, context.tenant_id)
        self.skus = ProductSkuRepository(session, context.tenant_id)
        self.categories = ProductCategoryRepository(session, context.tenant_id)
        self.brands = BrandRepository(session, context.tenant_id)

    def list_products(
        self,
        *,
        q: str | None = None,
        sku_code: str | None = None,
        category_id: int | None = None,
        brand_id: int | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductListOut:
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_READ,))
        if status and status not in {
            ProductStatus.DRAFT.value,
            ProductStatus.ACTIVE.value,
            ProductStatus.INACTIVE.value,
        }:
            raise AppError("商品状态不合法", code=40057, status_code=400)
        rows, total = self.products.list_page(
            q=(q or "").strip() or None,
            sku_code=(sku_code or "").strip() or None,
            category_id=category_id,
            brand_id=brand_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        items = [self._list_item(product, sku_count) for product, sku_count in rows]
        return ProductListOut(items=items, total=total, page=page, page_size=page_size)

    def get_product(self, product_id: int) -> ProductDetailOut:
        """按当前租户 + product_id 取详情。不能只按全局 id 查，否则会读到别的企业。"""
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_READ,))
        product = self.products.get_in_tenant(product_id)
        if product is None:
            raise AppError(_UNAVAILABLE, code=40432, status_code=404)
        return self._detail_out(product)

    def create_product(self, payload: ProductCreate) -> ProductDetailOut:
        """同一事务创建 SPU 和全部 SKU。

        功能：新建商品档案。
        参数：名称、内部编码、本租户类目/品牌、至少一个 SKU。
        返回：含 SKU 列表的详情。
        异常：类目/品牌不属于本租户 404；编码冲突 409；权限不足 403。
        关键流程：
        1. 先校验类目、品牌、SPU code、全部 sku_code（含本次请求内部重复）。
        2. 写入 Product 后 flush，才能拿到 product.id 填到 SKU 外键。
        3. 任一 SKU 失败则 rollback，避免「商品在、SKU 缺一半」。
        """
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_CREATE,))
        status = payload.status or ProductStatus.DRAFT.value
        if status not in {
            ProductStatus.DRAFT.value,
            ProductStatus.ACTIVE.value,
            ProductStatus.INACTIVE.value,
        }:
            raise AppError("商品状态不合法", code=40057, status_code=400)
        category = self.categories.get_in_tenant(payload.category_id)
        if category is None:
            raise AppError("类目不存在或不可访问", code=40430, status_code=404)
        brand = None
        if payload.brand_id is not None:
            brand = self.brands.get_in_tenant(payload.brand_id)
            if brand is None:
                raise AppError("品牌不存在或不可访问", code=40431, status_code=404)
        code = self._normalize_code(payload.code, field="商品编码")
        if self.products.get_by_code(code) is not None:
            raise AppError("商品编码已存在", code=40930, status_code=409)
        sku_codes = [self._normalize_code(item.sku_code, field="SKU 编码") for item in payload.skus]
        if len(sku_codes) != len(set(sku_codes)):
            raise AppError("SKU 编码不能重复", code=40931, status_code=409)
        for sku_code in sku_codes:
            if self.skus.get_by_code(sku_code) is not None:
                raise AppError("SKU 编码已存在", code=40931, status_code=409)
        product = Product(
            tenant_id=self.context.tenant_id,
            category_id=category.id,
            brand_id=brand.id if brand is not None else None,
            name=payload.name,
            code=code,
            description=payload.description,
            status=status,
        )
        try:
            self.products.add(product)
            # flush 后才有自增 id。现在 commit 的话 SKU 失败只能靠补偿删除，更容易留脏数据。
            self.session.flush()
            for item, sku_code in zip(payload.skus, sku_codes, strict=True):
                self.skus.add(self._new_sku(product.id, sku_code, item))
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError("商品或 SKU 编码已存在", code=40930, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
        created = self.products.get_in_tenant(product.id)
        if created is None:
            raise AppError(_UNAVAILABLE, code=40432, status_code=404)
        return self._detail_out(created)

    def update_product(self, product_id: int, payload: ProductUpdate) -> ProductDetailOut:
        """只改 SPU 字段。SKU 走子资源接口，避免一次 PATCH 语义含糊。"""
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_UPDATE,))
        product = self.products.get_in_tenant(product_id)
        if product is None:
            raise AppError(_UNAVAILABLE, code=40432, status_code=404)
        if payload.status is not None and payload.status not in {
            ProductStatus.DRAFT.value,
            ProductStatus.ACTIVE.value,
            ProductStatus.INACTIVE.value,
        }:
            raise AppError("商品状态不合法", code=40057, status_code=400)
        if payload.category_id is not None:
            category = self.categories.get_in_tenant(payload.category_id)
            if category is None:
                raise AppError("类目不存在或不可访问", code=40430, status_code=404)
            product.category_id = category.id
        if "brand_id" in payload.model_fields_set:
            if payload.brand_id is None:
                product.brand_id = None
            else:
                brand = self.brands.get_in_tenant(payload.brand_id)
                if brand is None:
                    raise AppError("品牌不存在或不可访问", code=40431, status_code=404)
                product.brand_id = brand.id
        if payload.name is not None:
            product.name = payload.name
        if "description" in payload.model_fields_set:
            product.description = payload.description
        if payload.status is not None:
            product.status = payload.status
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        reloaded = self.products.get_in_tenant(product_id)
        if reloaded is None:
            raise AppError(_UNAVAILABLE, code=40432, status_code=404)
        return self._detail_out(reloaded)

    def add_sku(self, product_id: int, payload: SkuInput) -> SkuOut:
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_UPDATE,))
        product = self.products.get_in_tenant(product_id)
        if product is None:
            raise AppError(_UNAVAILABLE, code=40432, status_code=404)
        sku_code = self._normalize_code(payload.sku_code, field="SKU 编码")
        if self.skus.get_by_code(sku_code) is not None:
            raise AppError("SKU 编码已存在", code=40931, status_code=409)
        sku = self._new_sku(product.id, sku_code, payload)
        try:
            self.skus.add(sku)
            self.session.commit()
            self.session.refresh(sku)
        except IntegrityError:
            self.session.rollback()
            raise AppError("SKU 编码已存在", code=40931, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
        return self._sku_out(sku)

    def update_sku(self, product_id: int, sku_id: int, payload: SkuUpdate) -> SkuOut:
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_UPDATE,))
        sku = self.skus.get_in_tenant(product_id=product_id, sku_id=sku_id)
        if sku is None:
            raise AppError(_UNAVAILABLE, code=40433, status_code=404)
        if payload.status is not None and payload.status not in {
            SkuStatus.ACTIVE.value,
            SkuStatus.INACTIVE.value,
        }:
            raise AppError("SKU 状态不合法", code=40057, status_code=400)
        if payload.name is not None:
            sku.name = payload.name
        if "barcode" in payload.model_fields_set:
            sku.barcode = payload.barcode
        if payload.spec_values is not None:
            sku.spec_values = self._clean_specs(payload.spec_values)
        if payload.status is not None:
            sku.status = payload.status
        try:
            self.session.commit()
            self.session.refresh(sku)
        except Exception:
            self.session.rollback()
            raise
        return self._sku_out(sku)

    def delete_sku(self, product_id: int, sku_id: int) -> None:
        """V3 尚无库存/订单引用，允许物理删除。

        一旦 SKU 产生库存或订单，应改为禁止删除、只停用。这里不提前建库存表。
        """
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_UPDATE,))
        sku = self.skus.get_in_tenant(product_id=product_id, sku_id=sku_id)
        if sku is None:
            raise AppError(_UNAVAILABLE, code=40433, status_code=404)
        remaining = [row for row in self.skus.list_for_product(product_id) if row.id != sku.id]
        if not remaining:
            raise AppError("商品至少保留一个 SKU", code=40058, status_code=400)
        try:
            self.skus.delete(sku)
            self.session.commit()
        except IntegrityError:
            # 未来库存/订单外键会打到这里。V3 没有这些表，这是给后续版本留的出口。
            self.session.rollback()
            raise AppError(
                "SKU 已被业务单据使用，不能删除，请停用。",
                code=40059,
                status_code=400,
            ) from None
        except Exception:
            self.session.rollback()
            raise

    def _new_sku(self, product_id: int, sku_code: str, payload: SkuInput) -> ProductSku:
        status = payload.status or SkuStatus.ACTIVE.value
        if status not in {SkuStatus.ACTIVE.value, SkuStatus.INACTIVE.value}:
            raise AppError("SKU 状态不合法", code=40057, status_code=400)
        return ProductSku(
            tenant_id=self.context.tenant_id,
            product_id=product_id,
            sku_code=sku_code,
            name=payload.name,
            barcode=payload.barcode,
            spec_values=self._clean_specs(payload.spec_values),
            status=status,
        )

    @staticmethod
    def _clean_specs(values: dict[str, Any]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for raw_key, raw_value in values.items():
            key = str(raw_key).strip()
            value = str(raw_value).strip() if raw_value is not None else ""
            if not key or not value:
                continue
            cleaned[key] = value
        return cleaned

    @staticmethod
    def _normalize_code(code: str, *, field: str) -> str:
        normalized = code.strip().upper()
        if not _PRODUCT_CODE.fullmatch(normalized):
            raise AppError(f"{field}不合法", code=40056, status_code=400)
        return normalized

    def _list_item(self, product: Product, sku_count: int) -> ProductListItem:
        return ProductListItem(
            id=product.id,
            tenant_id=product.tenant_id,
            name=product.name,
            code=product.code,
            category_id=product.category_id,
            category_name=product.category.name if product.category is not None else "",
            brand_id=product.brand_id,
            brand_name=product.brand.name if product.brand is not None else None,
            sku_count=sku_count,
            status=product.status,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

    def _detail_out(self, product: Product) -> ProductDetailOut:
        skus = sorted(product.skus, key=lambda item: item.id)
        return ProductDetailOut(
            id=product.id,
            tenant_id=product.tenant_id,
            name=product.name,
            code=product.code,
            category_id=product.category_id,
            category_name=product.category.name if product.category is not None else "",
            brand_id=product.brand_id,
            brand_name=product.brand.name if product.brand is not None else None,
            description=product.description,
            status=product.status,
            created_at=product.created_at,
            updated_at=product.updated_at,
            skus=[self._sku_out(item) for item in skus],
        )

    @staticmethod
    def _sku_out(sku: ProductSku) -> SkuOut:
        specs = sku.spec_values if isinstance(sku.spec_values, dict) else {}
        return SkuOut(
            id=sku.id,
            tenant_id=sku.tenant_id,
            product_id=sku.product_id,
            sku_code=sku.sku_code,
            name=sku.name,
            barcode=sku.barcode,
            spec_values=specs,
            status=sku.status,
            created_at=sku.created_at,
            updated_at=sku.updated_at,
        )
