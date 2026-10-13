from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    WarehouseCreateContext,
    WarehouseDeleteContext,
    WarehouseDisableContext,
    WarehouseReadContext,
    WarehouseUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.warehouse import (
    WarehouseCreate,
    WarehouseListOut,
    WarehouseOut,
    WarehouseStatusUpdate,
    WarehouseUpdate,
)
from app.services.warehouse import WarehouseService

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


@router.get("", response_model=ApiResponse[WarehouseListOut], summary="仓库列表")
def list_warehouses(
    context: WarehouseReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    warehouse_type: str | None = Query(default=None, max_length=16, alias="type"),
    status: str | None = Query(default=None, max_length=16),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[WarehouseListOut]:
    return ok(
        WarehouseService(session, context).list_warehouses(
            q=q,
            warehouse_type=warehouse_type,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{warehouse_id}", response_model=ApiResponse[WarehouseOut], summary="仓库详情")
def get_warehouse(
    warehouse_id: int,
    context: WarehouseReadContext,
    session: DbSession,
) -> ApiResponse[WarehouseOut]:
    return ok(WarehouseService(session, context).get_warehouse(warehouse_id))


@router.post("", response_model=ApiResponse[WarehouseOut], summary="新增仓库")
def create_warehouse(
    payload: WarehouseCreate,
    context: WarehouseCreateContext,
    session: DbSession,
) -> ApiResponse[WarehouseOut]:
    return ok(WarehouseService(session, context).create_warehouse(payload), "创建成功")


@router.patch("/{warehouse_id}", response_model=ApiResponse[WarehouseOut], summary="编辑仓库")
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    context: WarehouseUpdateContext,
    session: DbSession,
) -> ApiResponse[WarehouseOut]:
    return ok(WarehouseService(session, context).update_warehouse(warehouse_id, payload))


@router.patch(
    "/{warehouse_id}/status",
    response_model=ApiResponse[WarehouseOut],
    summary="启用或禁用仓库",
)
def change_warehouse_status(
    warehouse_id: int,
    payload: WarehouseStatusUpdate,
    context: WarehouseDisableContext,
    session: DbSession,
) -> ApiResponse[WarehouseOut]:
    return ok(WarehouseService(session, context).change_status(warehouse_id, payload))


@router.post(
    "/{warehouse_id}/set-default",
    response_model=ApiResponse[WarehouseOut],
    summary="设为默认仓库",
)
def set_default_warehouse(
    warehouse_id: int,
    context: WarehouseUpdateContext,
    session: DbSession,
) -> ApiResponse[WarehouseOut]:
    return ok(
        WarehouseService(session, context).set_default_warehouse(warehouse_id),
        "已设为默认仓库",
    )


@router.delete("/{warehouse_id}", response_model=ApiResponse[None], summary="删除仓库")
def delete_warehouse(
    warehouse_id: int,
    context: WarehouseDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    WarehouseService(session, context).delete_warehouse(warehouse_id)
    return ok(None, "已删除")
