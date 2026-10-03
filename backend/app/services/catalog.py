"""商品类目与品牌。Repository 不 commit；写操作由本层提交。"""

from __future__ import annotations

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.product import Brand, CatalogStatus, ProductCategory
from app.repositories.product import BrandRepository, ProductCategoryRepository, ProductRepository
from app.schemas.product import (
    BrandCreate,
    BrandListOut,
    BrandOut,
    BrandUpdate,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
)
from app.services.authorization import AuthorizationService

_BRAND_CODE = re.compile(r"^[A-Z][A-Z0-9_-]{0,31}$")
_MAX_LEVEL = 3
_UNAVAILABLE = "资源不存在或不可访问"


class CatalogService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService(session)
        self.categories = ProductCategoryRepository(session, context.tenant_id)
        self.brands = BrandRepository(session, context.tenant_id)
        self.products = ProductRepository(session, context.tenant_id)

    def list_category_tree(self) -> list[CategoryOut]:
        """把当前租户的扁平类目拼成最多三级的树。

        功能：一次查出本企业全部类目，在内存里按 parent_id 挂子节点。
        参数：无。租户来自 TenantContext，不读请求体里的 tenant_id。
        返回：根节点列表，每个节点带 children。
        异常：缺少 product:read 时 403。
        关键流程：先按 level/sort 排序，再挂到 parent。不要递归查库，否则 N+1。
        """
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_READ,))
        rows = self.categories.list_all()
        nodes = {row.id: self._category_out(row, children=[]) for row in rows}
        roots: list[CategoryOut] = []
        for row in rows:
            node = nodes[row.id]
            if row.parent_id is None:
                roots.append(node)
                continue
            parent = nodes.get(row.parent_id)
            # 父节点不在本租户结果里时丢到根下会暴露脏数据；直接跳过并保持隔离。
            if parent is None:
                continue
            parent.children.append(node)
        return roots

    def create_category(self, payload: CategoryCreate) -> CategoryOut:
        """新增类目。parent_id 必须指向本租户已有节点，且层级不超过 3。

        level 由父节点推算，不信任客户端传入。
        一级 parent_id 为空 → level=1；二级/三级 = parent.level + 1。
        parent.level 已经是 3 时拒绝，错误码 CATEGORY_MAX_DEPTH_EXCEEDED。
        本版不支持移动整棵子树，因此不必再算「带子节点搬家后是否超三级」。
        """
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_UPDATE,))
        parent: ProductCategory | None = None
        level = 1
        if payload.parent_id is not None:
            parent = self.categories.get_in_tenant(payload.parent_id)
            if parent is None:
                raise AppError(_UNAVAILABLE, code=40430, status_code=404)
            if parent.level >= _MAX_LEVEL:
                # 第三级已经是叶子。不能只靠前端藏按钮，直接调接口也必须拒绝。
                raise AppError(
                    "类目最多三级",
                    code=40053,
                    status_code=400,
                    data={"error": "CATEGORY_MAX_DEPTH_EXCEEDED"},
                )
            level = parent.level + 1
        if self.categories.find_sibling_name(parent_id=payload.parent_id, name=payload.name):
            raise AppError("同一父类目下名称不能重复", code=40054, status_code=400)
        category = ProductCategory(
            tenant_id=self.context.tenant_id,
            name=payload.name,
            parent_id=payload.parent_id,
            level=level,
            sort=payload.sort,
            status=CatalogStatus.ACTIVE.value,
        )
        try:
            self.categories.add(category)
            self.session.commit()
            self.session.refresh(category)
        except IntegrityError:
            self.session.rollback()
            raise AppError(_UNAVAILABLE, code=40430, status_code=404) from None
        except Exception:
            self.session.rollback()
            raise
        return self._category_out(category)

    def update_category(self, category_id: int, payload: CategoryUpdate) -> CategoryOut:
        """编辑名称 / 排序 / 状态。不改 parent_id，避免整棵树层级被悄悄打乱。"""
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_UPDATE,))
        category = self.categories.get_in_tenant(category_id)
        if category is None:
            raise AppError(_UNAVAILABLE, code=40430, status_code=404)
        if payload.status is not None and payload.status not in {
            CatalogStatus.ACTIVE.value,
            CatalogStatus.DISABLED.value,
        }:
            raise AppError("类目状态不合法", code=40055, status_code=400)
        if payload.name is not None:
            dup = self.categories.find_sibling_name(
                parent_id=category.parent_id,
                name=payload.name,
                exclude_id=category.id,
            )
            if dup is not None:
                raise AppError("同一父类目下名称不能重复", code=40054, status_code=400)
            category.name = payload.name
        if payload.sort is not None:
            category.sort = payload.sort
        if payload.status is not None:
            category.status = payload.status
        try:
            self.session.commit()
            self.session.refresh(category)
        except Exception:
            self.session.rollback()
            raise
        return self._category_out(category)

    def delete_category(self, category_id: int) -> None:
        """删除类目。有子节点或已被商品使用时拒绝，避免级联毁掉商品。"""
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_DELETE,))
        category = self.categories.get_in_tenant(category_id)
        if category is None:
            raise AppError(_UNAVAILABLE, code=40430, status_code=404)
        # 先查子类目。若直接删父节点，子节点的 parent_id 会变成悬空或被数据库拒绝。
        children = self.categories.count_children(category.id)
        if children > 0:
            raise AppError(
                f"当前类目下仍有 {children} 个子类目，请先删除或调整子类目。",
                code=40050,
                status_code=400,
                data={"error": "CATEGORY_HAS_CHILDREN", "child_count": children},
            )
        used = self.products.count_by_category(category.id)
        if used > 0:
            raise AppError(
                f"当前类目仍有 {used} 个商品使用，不能删除。",
                code=40051,
                status_code=400,
                data={"error": "CATEGORY_IN_USE", "product_count": used},
            )
        try:
            self.categories.delete(category)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "当前类目仍被商品使用，不能删除。",
                code=40051,
                status_code=400,
                data={"error": "CATEGORY_IN_USE"},
            ) from None
        except Exception:
            self.session.rollback()
            raise

    def list_brands(
        self,
        *,
        q: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> BrandListOut:
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_READ,))
        if status and status not in {CatalogStatus.ACTIVE.value, CatalogStatus.DISABLED.value}:
            raise AppError("品牌状态不合法", code=40055, status_code=400)
        rows, total = self.brands.list_page(
            q=(q or "").strip() or None,
            status=status,
            page=page,
            page_size=page_size,
        )
        return BrandListOut(
            items=[self._brand_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_brand_options(self) -> list[BrandOut]:
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_READ,))
        return [self._brand_out(row) for row in self.brands.list_all_active()]

    def create_brand(self, payload: BrandCreate) -> BrandOut:
        """新增本租户品牌。code 先规范化再查重，避免大小写各写一行。"""
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_UPDATE,))
        code = self._normalize_brand_code(payload.code)
        if self.brands.get_by_code(code) is not None:
            raise AppError("品牌编码已存在", code=40932, status_code=409)
        brand = Brand(
            tenant_id=self.context.tenant_id,
            name=payload.name,
            code=code,
            logo_url=payload.logo_url,
            description=payload.description,
            status=CatalogStatus.ACTIVE.value,
        )
        try:
            self.brands.add(brand)
            self.session.commit()
            self.session.refresh(brand)
        except IntegrityError:
            self.session.rollback()
            raise AppError("品牌编码已存在", code=40932, status_code=409) from None
        except Exception:
            self.session.rollback()
            raise
        return self._brand_out(brand)

    def update_brand(self, brand_id: int, payload: BrandUpdate) -> BrandOut:
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_UPDATE,))
        brand = self.brands.get_in_tenant(brand_id)
        if brand is None:
            raise AppError(_UNAVAILABLE, code=40431, status_code=404)
        if payload.status is not None and payload.status not in {
            CatalogStatus.ACTIVE.value,
            CatalogStatus.DISABLED.value,
        }:
            raise AppError("品牌状态不合法", code=40055, status_code=400)
        if payload.name is not None:
            brand.name = payload.name
        if "logo_url" in payload.model_fields_set:
            brand.logo_url = payload.logo_url
        if "description" in payload.model_fields_set:
            brand.description = payload.description
        if payload.status is not None:
            brand.status = payload.status
        try:
            self.session.commit()
            self.session.refresh(brand)
        except Exception:
            self.session.rollback()
            raise
        return self._brand_out(brand)

    def delete_brand(self, brand_id: int) -> None:
        """删除品牌。已被商品引用时拒绝，不级联改商品。"""
        self.auth.require_all(self.context, (PermissionCode.PRODUCT_DELETE,))
        brand = self.brands.get_in_tenant(brand_id)
        if brand is None:
            raise AppError(_UNAVAILABLE, code=40431, status_code=404)
        used = self.products.count_by_brand(brand.id)
        if used > 0:
            raise AppError(
                f"当前品牌仍有 {used} 个商品使用，不能删除。",
                code=40052,
                status_code=400,
                data={"error": "BRAND_IN_USE", "product_count": used},
            )
        try:
            self.brands.delete(brand)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "当前品牌仍被商品使用，不能删除。",
                code=40052,
                status_code=400,
                data={"error": "BRAND_IN_USE"},
            ) from None
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _normalize_brand_code(code: str) -> str:
        normalized = code.strip().upper()
        if not _BRAND_CODE.fullmatch(normalized):
            raise AppError("品牌编码不合法", code=40056, status_code=400)
        return normalized

    @staticmethod
    def _category_out(
        row: ProductCategory,
        children: list[CategoryOut] | None = None,
    ) -> CategoryOut:
        return CategoryOut(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            parent_id=row.parent_id,
            level=row.level,
            sort=row.sort,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            children=children or [],
        )

    @staticmethod
    def _brand_out(row: Brand) -> BrandOut:
        return BrandOut(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            code=row.code,
            logo_url=row.logo_url,
            description=row.description,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
