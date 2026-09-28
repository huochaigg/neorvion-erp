from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import ProductCreateContext, ProductReadContext, ProductUpdateContext
from app.schemas.common import ApiResponse, ok
from app.schemas.product import (
    ProductCreate,
    ProductDetailOut,
    ProductListOut,
    ProductUpdate,
    SkuInput,
    SkuOut,
    SkuUpdate,
)
from app.services.product import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ApiResponse[ProductListOut], summary="商品列表")
def list_products(
    context: ProductReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    sku_code: str | None = Query(default=None, max_length=64),
    category_id: int | None = Query(default=None, gt=0),
    brand_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[ProductListOut]:
    return ok(
        ProductService(session, context).list_products(
            q=q,
            sku_code=sku_code,
            category_id=category_id,
            brand_id=brand_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


@router.post("", response_model=ApiResponse[ProductDetailOut], summary="创建商品")
def create_product(
    payload: ProductCreate,
    context: ProductCreateContext,
    session: DbSession,
) -> ApiResponse[ProductDetailOut]:
    return ok(ProductService(session, context).create_product(payload), "创建成功")


@router.get("/{product_id}", response_model=ApiResponse[ProductDetailOut], summary="商品详情")
def get_product(
    product_id: int,
    context: ProductReadContext,
    session: DbSession,
) -> ApiResponse[ProductDetailOut]:
    return ok(ProductService(session, context).get_product(product_id))


@router.patch("/{product_id}", response_model=ApiResponse[ProductDetailOut], summary="编辑商品")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    context: ProductUpdateContext,
    session: DbSession,
) -> ApiResponse[ProductDetailOut]:
    return ok(ProductService(session, context).update_product(product_id, payload))


@router.post("/{product_id}/skus", response_model=ApiResponse[SkuOut], summary="新增 SKU")
def add_sku(
    product_id: int,
    payload: SkuInput,
    context: ProductUpdateContext,
    session: DbSession,
) -> ApiResponse[SkuOut]:
    return ok(ProductService(session, context).add_sku(product_id, payload), "已添加")


@router.patch("/{product_id}/skus/{sku_id}", response_model=ApiResponse[SkuOut], summary="编辑 SKU")
def update_sku(
    product_id: int,
    sku_id: int,
    payload: SkuUpdate,
    context: ProductUpdateContext,
    session: DbSession,
) -> ApiResponse[SkuOut]:
    return ok(ProductService(session, context).update_sku(product_id, sku_id, payload))


@router.delete("/{product_id}/skus/{sku_id}", response_model=ApiResponse[None], summary="删除 SKU")
def delete_sku(
    product_id: int,
    sku_id: int,
    context: ProductUpdateContext,
    session: DbSession,
) -> ApiResponse[None]:
    ProductService(session, context).delete_sku(product_id, sku_id)
    return ok(None, "已删除")
