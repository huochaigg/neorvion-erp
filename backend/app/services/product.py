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
_AUTO_PRODUCT_PREFIX = "PD"
_AUTO_SKU_PREFIX = "SKU"
_AUTO_CODE_WIDTH = 10


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
        """同一事务创建 SPU 和全部 SKU。编码可空，flush 后用自增 id 生成。

        功能：新建商品档案。
        参数：名称、可选内部编码、本租户类目/品牌、至少一个 SKU。
        返回：含最终 code / sku_code / barcode 的详情。
        异常：类目/品牌不属于本租户 404；编码冲突 409；权限不足 403。

        事务关系（务必读懂）：
        - session.add：只把对象登记到 Session，此时还没有 INSERT，也没有 id。
        - session.flush：把待插入的 SQL 发给数据库，自增主键立刻回到对象上。
          flush 不是提交。当前事务仍未结束，别的连接默认读不到这些行。
        - session.commit：事务成功结束，编码和 SKU 一起永久生效。
        - session.rollback：无论是否已经 flush，未 commit 的 Product 和 SKU 全部撤销。
          所以第二个 SKU 失败时，已经拿到 id 的 Product 也不会留下半成品。

        为什么不用 SELECT MAX(code)+1：
        两个请求同时读到同一个最大值，会生成相同编码，撞 UNIQUE(tenant_id, code)。
        自增 id 由数据库分配，并发下也不会重复，适合作为编号来源。
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

        # 用户填了才规范化并查重；空值留给 flush 后按 id 生成。
        custom_code = self._normalize_optional_code(payload.code, field="商品编码")
        if custom_code is not None and self.products.get_by_code(custom_code) is not None:
            raise AppError("商品编码已存在", code=40930, status_code=409)

        sku_codes = [
            self._normalize_optional_code(item.sku_code, field="SKU 编码")
            for item in payload.skus
        ]
        provided_sku_codes = [code for code in sku_codes if code is not None]
        if len(provided_sku_codes) != len(set(provided_sku_codes)):
            raise AppError("SKU 编码不能重复", code=40931, status_code=409)
        for sku_code in provided_sku_codes:
            if self.skus.get_by_code(sku_code) is not None:
                raise AppError("SKU 编码已存在", code=40931, status_code=409)

        product = Product(
            tenant_id=self.context.tenant_id,
            category_id=category.id,
            brand_id=brand.id if brand is not None else None,
            name=payload.name,
            code=custom_code,
            description=payload.description,
            status=status,
        )
        created_skus: list[ProductSku] = []
        try:
            self.products.add(product)
            # 先 flush Product：没有 id 就无法写 SKU 外键，也无法生成 PD{id}。
            self.session.flush()
            if product.code is None:
                product.code = self._auto_product_code(product.id)

            for item, sku_code in zip(payload.skus, sku_codes, strict=True):
                sku = self._new_sku(product.id, sku_code, item)
                self.skus.add(sku)
                created_skus.append(sku)
            # 一次 flush 给本批 SKU 全部拿到 id，再按最终 sku_code 填 barcode。
            self.session.flush()
            for sku in created_skus:
                self._apply_sku_identity(sku)

            if product.code is None:
                raise AppError("商品编码生成失败", code=50021, status_code=500)
            self.session.commit()
        except IntegrityError:
            # 应用层查重与提交之间可能有并发写入；数据库 UNIQUE 是最后防线。
            # rollback 会撤销本次 flush 过的 Product / SKU，不会留下空编码行。
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
        sku_code = self._normalize_optional_code(payload.sku_code, field="SKU 编码")
        if sku_code is not None and self.skus.get_by_code(sku_code) is not None:
            raise AppError("SKU 编码已存在", code=40931, status_code=409)
        sku = self._new_sku(product.id, sku_code, payload)
        try:
            self.skus.add(sku)
            self.session.flush()
            self._apply_sku_identity(sku)
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
        # model_fields_set：PATCH 里写了 barcode（含显式 null）才改；没提交则保持原值。
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

    def _new_sku(self, product_id: int, sku_code: str | None, payload: SkuInput) -> ProductSku:
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
    def _auto_product_code(product_id: int) -> str:
        return f"{_AUTO_PRODUCT_PREFIX}{product_id:0{_AUTO_CODE_WIDTH}d}"

    @staticmethod
    def _auto_sku_code(sku_id: int) -> str:
        return f"{_AUTO_SKU_PREFIX}{sku_id:0{_AUTO_CODE_WIDTH}d}"

    def _apply_sku_identity(self, sku: ProductSku) -> None:
        """flush 拿到 sku.id 之后补编码。barcode 必须用最终 sku_code，不能在生成前赋空。

        用户填了 sku_code：保留（已规范化）。
        用户没填：SKU + 10 位 id。
        用户填了 barcode：保留。
        用户没填：等于最终 sku_code。
        """
        if not sku.sku_code:
            sku.sku_code = self._auto_sku_code(sku.id)
        if sku.barcode is None:
            sku.barcode = sku.sku_code

    def _normalize_optional_code(self, code: str | None, *, field: str) -> str | None:
        if code is None:
            return None
        text = code.strip()
        if not text:
            return None
        return self._normalize_code(text, field=field)

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
            code=product.code or "",
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
            code=product.code or "",
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
            sku_code=sku.sku_code or "",
            name=sku.name,
            barcode=sku.barcode,
            spec_values=specs,
            status=sku.status,
            created_at=sku.created_at,
            updated_at=sku.updated_at,
        )
