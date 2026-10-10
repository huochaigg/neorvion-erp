from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    StocktakeCancelContext,
    StocktakeConfirmContext,
    StocktakeCreateContext,
    StocktakeReadContext,
    StocktakeSubmitContext,
    StocktakeUpdateContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.stocktake import (
    StocktakeCreate,
    StocktakeItemPatch,
    StocktakeItemsSave,
    StocktakeListOut,
    StocktakeOut,
    StocktakeUpdate,
)
from app.services.stocktake import StocktakeService

router = APIRouter(prefix="/stocktakes", tags=["stocktakes"])


@router.get("", response_model=ApiResponse[StocktakeListOut], summary="盘点单列表")
def list_stocktakes(
    context: StocktakeReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    warehouse_id: int | None = Query(default=None, gt=0),
    status: str | None = Query(default=None, max_length=24),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[StocktakeListOut]:
    data = StocktakeService(session, context).list_stocktakes(
        q=(q or "").strip() or None,
        warehouse_id=warehouse_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    return ok(data)


@router.post("", response_model=ApiResponse[StocktakeOut], summary="创建盘点任务")
def create_stocktake(
    payload: StocktakeCreate,
    context: StocktakeCreateContext,
    session: DbSession,
) -> ApiResponse[StocktakeOut]:
    return ok(StocktakeService(session, context).create_stocktake(payload))


@router.get("/{stocktake_id}", response_model=ApiResponse[StocktakeOut], summary="盘点单详情")
def get_stocktake(
    stocktake_id: int,
    context: StocktakeReadContext,
    session: DbSession,
) -> ApiResponse[StocktakeOut]:
    return ok(StocktakeService(session, context).get_stocktake(stocktake_id))


@router.patch("/{stocktake_id}", response_model=ApiResponse[StocktakeOut], summary="修改盘点备注")
def update_stocktake(
    stocktake_id: int,
    payload: StocktakeUpdate,
    context: StocktakeUpdateContext,
    session: DbSession,
) -> ApiResponse[StocktakeOut]:
    return ok(StocktakeService(session, context).update_stocktake(stocktake_id, payload))


@router.put(
    "/{stocktake_id}/items",
    response_model=ApiResponse[StocktakeOut],
    summary="批量保存实盘数量",
)
def save_stocktake_items(
    stocktake_id: int,
    payload: StocktakeItemsSave,
    context: StocktakeUpdateContext,
    session: DbSession,
) -> ApiResponse[StocktakeOut]:
    return ok(StocktakeService(session, context).save_items(stocktake_id, payload))


@router.patch(
    "/{stocktake_id}/items/{item_id}",
    response_model=ApiResponse[StocktakeOut],
    summary="保存一条实盘数量",
)
def update_stocktake_item(
    stocktake_id: int,
    item_id: int,
    payload: StocktakeItemPatch,
    context: StocktakeUpdateContext,
    session: DbSession,
) -> ApiResponse[StocktakeOut]:
    return ok(StocktakeService(session, context).update_item(stocktake_id, item_id, payload))


@router.post(
    "/{stocktake_id}/submit",
    response_model=ApiResponse[StocktakeOut],
    summary="提交盘点",
)
def submit_stocktake(
    stocktake_id: int,
    context: StocktakeSubmitContext,
    session: DbSession,
) -> ApiResponse[StocktakeOut]:
    return ok(StocktakeService(session, context).submit_stocktake(stocktake_id))


@router.post(
    "/{stocktake_id}/confirm",
    response_model=ApiResponse[StocktakeOut],
    summary="确认盘点并按差异调整库存",
)
def confirm_stocktake(
    stocktake_id: int,
    context: StocktakeConfirmContext,
    session: DbSession,
) -> ApiResponse[StocktakeOut]:
    return ok(StocktakeService(session, context).confirm_stocktake(stocktake_id))


@router.post(
    "/{stocktake_id}/cancel",
    response_model=ApiResponse[StocktakeOut],
    summary="取消尚未确认的盘点",
)
def cancel_stocktake(
    stocktake_id: int,
    context: StocktakeCancelContext,
    session: DbSession,
) -> ApiResponse[StocktakeOut]:
    return ok(StocktakeService(session, context).cancel_stocktake(stocktake_id))
