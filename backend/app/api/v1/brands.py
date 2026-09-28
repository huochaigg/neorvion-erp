from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import ProductDeleteContext, ProductReadContext, ProductUpdateContext
from app.schemas.common import ApiResponse, ok
from app.schemas.product import BrandCreate, BrandListOut, BrandOut, BrandUpdate
from app.services.catalog import CatalogService

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("", response_model=ApiResponse[BrandListOut], summary="品牌列表")
def list_brands(
    context: ProductReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[BrandListOut]:
    return ok(
        CatalogService(session, context).list_brands(
            q=q,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/options", response_model=ApiResponse[list[BrandOut]], summary="品牌选项")
def list_brand_options(
    context: ProductReadContext,
    session: DbSession,
) -> ApiResponse[list[BrandOut]]:
    return ok(CatalogService(session, context).list_brand_options())


@router.post("", response_model=ApiResponse[BrandOut], summary="新增品牌")
def create_brand(
    payload: BrandCreate,
    context: ProductUpdateContext,
    session: DbSession,
) -> ApiResponse[BrandOut]:
    return ok(CatalogService(session, context).create_brand(payload), "创建成功")


@router.patch("/{brand_id}", response_model=ApiResponse[BrandOut], summary="编辑品牌")
def update_brand(
    brand_id: int,
    payload: BrandUpdate,
    context: ProductUpdateContext,
    session: DbSession,
) -> ApiResponse[BrandOut]:
    return ok(CatalogService(session, context).update_brand(brand_id, payload))


@router.delete("/{brand_id}", response_model=ApiResponse[None], summary="删除品牌")
def delete_brand(
    brand_id: int,
    context: ProductDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    CatalogService(session, context).delete_brand(brand_id)
    return ok(None, "已删除")
