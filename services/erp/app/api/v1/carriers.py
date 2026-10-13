from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    CarrierCreateContext,
    CarrierDeleteContext,
    CarrierDisableContext,
    CarrierReadContext,
    CarrierUpdateContext,
)
from app.schemas.carrier import (
    CarrierCreate,
    CarrierListOut,
    CarrierOut,
    CarrierStatusUpdate,
    CarrierUpdate,
)
from app.schemas.common import ApiResponse, ok
from app.services.carrier import CarrierService

router = APIRouter(prefix="/carriers", tags=["carriers"])


@router.get("", response_model=ApiResponse[CarrierListOut], summary="物流商列表")
def list_carriers(
    context: CarrierReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    carrier_type: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[CarrierListOut]:
    return ok(
        CarrierService(session, context).list_carriers(
            q=q,
            status=status,
            carrier_type=carrier_type,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{carrier_id}", response_model=ApiResponse[CarrierOut], summary="物流商详情")
def get_carrier(
    carrier_id: int,
    context: CarrierReadContext,
    session: DbSession,
) -> ApiResponse[CarrierOut]:
    return ok(CarrierService(session, context).get_carrier(carrier_id))


@router.post("", response_model=ApiResponse[CarrierOut], summary="新增物流商")
def create_carrier(
    payload: CarrierCreate,
    context: CarrierCreateContext,
    session: DbSession,
) -> ApiResponse[CarrierOut]:
    return ok(CarrierService(session, context).create_carrier(payload), "创建成功")


@router.patch("/{carrier_id}", response_model=ApiResponse[CarrierOut], summary="编辑物流商")
def update_carrier(
    carrier_id: int,
    payload: CarrierUpdate,
    context: CarrierUpdateContext,
    session: DbSession,
) -> ApiResponse[CarrierOut]:
    return ok(CarrierService(session, context).update_carrier(carrier_id, payload))


@router.patch(
    "/{carrier_id}/status",
    response_model=ApiResponse[CarrierOut],
    summary="启用或禁用物流商",
)
def change_carrier_status(
    carrier_id: int,
    payload: CarrierStatusUpdate,
    context: CarrierDisableContext,
    session: DbSession,
) -> ApiResponse[CarrierOut]:
    return ok(CarrierService(session, context).change_status(carrier_id, payload))


@router.delete("/{carrier_id}", response_model=ApiResponse[None], summary="删除物流商")
def delete_carrier(
    carrier_id: int,
    context: CarrierDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    CarrierService(session, context).delete_carrier(carrier_id)
    return ok(None, "已删除")
