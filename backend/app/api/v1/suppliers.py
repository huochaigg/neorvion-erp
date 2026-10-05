from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    SupplierCreateContext,
    SupplierDeleteContext,
    SupplierDisableContext,
    SupplierReadContext,
    SupplierUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.supplier import (
    SupplierCreate,
    SupplierListOut,
    SupplierOut,
    SupplierStatusUpdate,
    SupplierUpdate,
)
from app.services.supplier import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=ApiResponse[SupplierListOut], summary="供应商列表")
def list_suppliers(
    context: SupplierReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    country_code: str | None = Query(default=None, max_length=2),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[SupplierListOut]:
    return ok(
        SupplierService(session, context).list_suppliers(
            q=q,
            status=status,
            country_code=country_code,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{supplier_id}", response_model=ApiResponse[SupplierOut], summary="供应商详情")
def get_supplier(
    supplier_id: int,
    context: SupplierReadContext,
    session: DbSession,
) -> ApiResponse[SupplierOut]:
    return ok(SupplierService(session, context).get_supplier(supplier_id))


@router.post("", response_model=ApiResponse[SupplierOut], summary="新增供应商")
def create_supplier(
    payload: SupplierCreate,
    context: SupplierCreateContext,
    session: DbSession,
) -> ApiResponse[SupplierOut]:
    return ok(SupplierService(session, context).create_supplier(payload), "创建成功")


@router.patch("/{supplier_id}", response_model=ApiResponse[SupplierOut], summary="编辑供应商")
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    context: SupplierUpdateContext,
    session: DbSession,
) -> ApiResponse[SupplierOut]:
    return ok(SupplierService(session, context).update_supplier(supplier_id, payload))


@router.patch(
    "/{supplier_id}/status",
    response_model=ApiResponse[SupplierOut],
    summary="启用或禁用供应商",
)
def change_supplier_status(
    supplier_id: int,
    payload: SupplierStatusUpdate,
    context: SupplierDisableContext,
    session: DbSession,
) -> ApiResponse[SupplierOut]:
    return ok(SupplierService(session, context).change_status(supplier_id, payload))


@router.delete("/{supplier_id}", response_model=ApiResponse[None], summary="删除供应商")
def delete_supplier(
    supplier_id: int,
    context: SupplierDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    SupplierService(session, context).delete_supplier(supplier_id)
    return ok(None, "已删除")
