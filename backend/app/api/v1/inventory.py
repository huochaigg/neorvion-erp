from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.rbac_deps import (
    InventoryAdjustContext,
    InventoryInitializeContext,
    InventoryReadContext,
    InventoryTransactionReadContext,
    ProductReadContext,
)
from app.schemas.common import ApiResponse, ok
from app.schemas.inventory import (
    InventoryAdjust,
    InventoryDetailOut,
    InventoryInitialize,
    InventoryItemOut,
    InventoryListOut,
    InventoryOptimisticAdjust,
    InventoryQtyChange,
    InventoryTransactionListOut,
    SkuOptionListOut,
)
from app.services.inventory import InventoryService

router = APIRouter(prefix="/inventory", tags=["inventory"])
sku_router = APIRouter(prefix="/product-skus", tags=["product-skus"])


@sku_router.get("", response_model=ApiResponse[SkuOptionListOut], summary="SKU 远程搜索")
def search_product_skus(
    context: ProductReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[SkuOptionListOut]:
    return ok(
        InventoryService(session, context).search_sku_options(q=q, page=page, page_size=page_size)
    )


@router.get("", response_model=ApiResponse[InventoryListOut], summary="库存列表")
def list_inventory(
    context: InventoryReadContext,
    session: DbSession,
    q: str | None = Query(default=None, max_length=64),
    sku_code: str | None = Query(default=None, max_length=64),
    warehouse_id: int | None = Query(default=None, gt=0),
    category_id: int | None = Query(default=None, gt=0),
    brand_id: int | None = Query(default=None, gt=0),
    stock_status: str | None = Query(default=None, max_length=16),
    threshold: int = Query(default=10, ge=0, le=100000),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[InventoryListOut]:
    return ok(
        InventoryService(session, context).list_inventory(
            q=q,
            sku_code=sku_code,
            warehouse_id=warehouse_id,
            category_id=category_id,
            brand_id=brand_id,
            stock_status=stock_status,
            threshold=threshold,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/initialize", response_model=ApiResponse[InventoryItemOut], summary="初始化库存")
def initialize_inventory(
    payload: InventoryInitialize,
    context: InventoryInitializeContext,
    session: DbSession,
) -> ApiResponse[InventoryItemOut]:
    return ok(InventoryService(session, context).initialize_inventory(payload), "初始化成功")


@router.get(
    "/transactions",
    response_model=ApiResponse[InventoryTransactionListOut],
    summary="库存流水",
)
def list_all_transactions(
    context: InventoryTransactionReadContext,
    session: DbSession,
    warehouse_id: int | None = Query(default=None, gt=0),
    sku_id: int | None = Query(default=None, gt=0),
    tx_type: str | None = Query(default=None, max_length=16, alias="type"),
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[InventoryTransactionListOut]:
    return ok(
        InventoryService(session, context).list_transactions(
            inventory_id=None,
            warehouse_id=warehouse_id,
            sku_id=sku_id,
            tx_type=tx_type,
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{inventory_id}", response_model=ApiResponse[InventoryDetailOut], summary="库存详情")
def get_inventory(
    inventory_id: int,
    context: InventoryReadContext,
    session: DbSession,
) -> ApiResponse[InventoryDetailOut]:
    return ok(InventoryService(session, context).get_inventory(inventory_id))


@router.post(
    "/{inventory_id}/adjust",
    response_model=ApiResponse[InventoryItemOut],
    summary="库存调整",
)
def adjust_inventory(
    inventory_id: int,
    payload: InventoryAdjust,
    context: InventoryAdjustContext,
    session: DbSession,
) -> ApiResponse[InventoryItemOut]:
    return ok(
        InventoryService(session, context).adjust_inventory(inventory_id, payload),
        "调整成功",
    )


@router.get(
    "/{inventory_id}/transactions",
    response_model=ApiResponse[InventoryTransactionListOut],
    summary="单条库存流水",
)
def list_inventory_transactions(
    inventory_id: int,
    context: InventoryTransactionReadContext,
    session: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[InventoryTransactionListOut]:
    return ok(
        InventoryService(session, context).list_transactions(
            inventory_id=inventory_id,
            warehouse_id=None,
            sku_id=None,
            tx_type=None,
            created_from=None,
            created_to=None,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/{inventory_id}/reserve",
    response_model=ApiResponse[InventoryItemOut],
    summary="预占库存（内部能力，不进业务菜单）",
)
def reserve_inventory(
    inventory_id: int,
    payload: InventoryQtyChange,
    context: InventoryAdjustContext,
    session: DbSession,
) -> ApiResponse[InventoryItemOut]:
    return ok(InventoryService(session, context).reserve_inventory(inventory_id, payload))


@router.post(
    "/{inventory_id}/release",
    response_model=ApiResponse[InventoryItemOut],
    summary="释放预占（内部能力，不进业务菜单）",
)
def release_inventory(
    inventory_id: int,
    payload: InventoryQtyChange,
    context: InventoryAdjustContext,
    session: DbSession,
) -> ApiResponse[InventoryItemOut]:
    return ok(InventoryService(session, context).release_inventory(inventory_id, payload))


@router.post(
    "/{inventory_id}/deduct-reserved",
    response_model=ApiResponse[InventoryItemOut],
    summary="确认出库扣减（内部能力，不进业务菜单）",
)
def deduct_reserved_inventory(
    inventory_id: int,
    payload: InventoryQtyChange,
    context: InventoryAdjustContext,
    session: DbSession,
) -> ApiResponse[InventoryItemOut]:
    return ok(InventoryService(session, context).deduct_reserved_inventory(inventory_id, payload))


@router.post(
    "/{inventory_id}/optimistic-adjust",
    response_model=ApiResponse[InventoryItemOut],
    summary="乐观锁调整演示（不进业务菜单）",
)
def optimistic_adjust_inventory(
    inventory_id: int,
    payload: InventoryOptimisticAdjust,
    context: InventoryAdjustContext,
    session: DbSession,
) -> ApiResponse[InventoryItemOut]:
    return ok(InventoryService(session, context).adjust_inventory_optimistic(inventory_id, payload))
