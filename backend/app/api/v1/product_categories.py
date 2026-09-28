from fastapi import APIRouter

from app.api.deps import DbSession
from app.api.rbac_deps import ProductDeleteContext, ProductReadContext, ProductUpdateContext
from app.schemas.common import ApiResponse, ok
from app.schemas.product import CategoryCreate, CategoryOut, CategoryUpdate
from app.services.catalog import CatalogService

router = APIRouter(prefix="/product-categories", tags=["product-categories"])


@router.get("", response_model=ApiResponse[list[CategoryOut]], summary="类目树")
def list_categories(
    context: ProductReadContext,
    session: DbSession,
) -> ApiResponse[list[CategoryOut]]:
    return ok(CatalogService(session, context).list_category_tree())


@router.post("", response_model=ApiResponse[CategoryOut], summary="新增类目")
def create_category(
    payload: CategoryCreate,
    context: ProductUpdateContext,
    session: DbSession,
) -> ApiResponse[CategoryOut]:
    return ok(CatalogService(session, context).create_category(payload), "创建成功")


@router.patch("/{category_id}", response_model=ApiResponse[CategoryOut], summary="编辑类目")
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    context: ProductUpdateContext,
    session: DbSession,
) -> ApiResponse[CategoryOut]:
    return ok(CatalogService(session, context).update_category(category_id, payload))


@router.delete("/{category_id}", response_model=ApiResponse[None], summary="删除类目")
def delete_category(
    category_id: int,
    context: ProductDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    CatalogService(session, context).delete_category(category_id)
    return ok(None, "已删除")
