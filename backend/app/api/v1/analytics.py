from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.deps import DbSession
from app.api.rbac_deps import (
    AnalyticsAfterSaleReadContext,
    AnalyticsInventoryReadContext,
    AnalyticsOverviewReadContext,
    AnalyticsPurchaseReadContext,
    AnalyticsSalesReadContext,
)
from app.schemas.analytics import (
    AfterSaleSummaryOut,
    AfterSaleTrendPoint,
    AfterSaleTypeCountOut,
    InventorySkuOut,
    InventorySummaryOut,
    OverviewOut,
    PendingCountsOut,
    PurchaseSummaryOut,
    PurchaseTrendPoint,
    SalesSummaryOut,
    SalesTrendPoint,
    StatusCountOut,
    TopCustomerOut,
    TopProductOut,
    TopSkuOut,
    TopSupplierOut,
    TransactionTrendPoint,
    TransactionTypePoint,
    WarehouseInventorySummaryOut,
)
from app.schemas.async_task import AsyncTaskOut, ReportExportCreate
from app.schemas.common import ApiResponse, ok
from app.services.analytics import AnalyticsService
from app.services.async_task import AsyncTaskService

router = APIRouter(prefix="/analytics", tags=["analytics"])

StartDate = Annotated[str | None, Query(description="开始日期 YYYY-MM-DD，含当天 00:00:00")]
EndDate = Annotated[
    str | None, Query(description="结束日期 YYYY-MM-DD，统计到当天结束（次日 00:00:00 不含）")
]
WarehouseId = Annotated[int | None, Query(gt=0, description="可选仓库过滤")]
Limit = Annotated[int, Query(ge=1, le=20, description="Top N，默认 10，最大 20")]
Threshold = Annotated[int, Query(ge=0, description="低库存阈值，比较 available_quantity，默认 10")]


def _csv_response(filename: str, content: str) -> Response:
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/overview", response_model=ApiResponse[OverviewOut], summary="经营总览")
def overview(
    context: AnalyticsOverviewReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
    low_stock_threshold: Threshold = 10,
) -> ApiResponse[OverviewOut]:
    data = AnalyticsService(session, context).overview(
        start_date, end_date, warehouse_id, low_stock_threshold
    )
    return ok(data)


@router.get("/pending", response_model=ApiResponse[PendingCountsOut], summary="待处理事项")
def pending(
    context: AnalyticsOverviewReadContext,
    session: DbSession,
    warehouse_id: WarehouseId = None,
    low_stock_threshold: Threshold = 10,
) -> ApiResponse[PendingCountsOut]:
    return ok(AnalyticsService(session, context).pending(warehouse_id, low_stock_threshold))


@router.get("/sales/summary", response_model=ApiResponse[SalesSummaryOut], summary="销售 KPI")
def sales_summary(
    context: AnalyticsSalesReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[SalesSummaryOut]:
    return ok(AnalyticsService(session, context).sales_summary(start_date, end_date, warehouse_id))


@router.get("/sales/trend", response_model=ApiResponse[list[SalesTrendPoint]], summary="销售趋势")
def sales_trend(
    context: AnalyticsSalesReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[SalesTrendPoint]]:
    return ok(AnalyticsService(session, context).sales_trend(start_date, end_date, warehouse_id))


@router.get(
    "/sales/status", response_model=ApiResponse[list[StatusCountOut]], summary="销售订单状态分布"
)
def sales_status(
    context: AnalyticsSalesReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[StatusCountOut]]:
    return ok(
        AnalyticsService(session, context).sales_status_distribution(
            start_date, end_date, warehouse_id
        )
    )


@router.get("/sales/top-skus", response_model=ApiResponse[list[TopSkuOut]], summary="销售 Top SKU")
def sales_top_skus(
    context: AnalyticsSalesReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
    limit: Limit = 10,
) -> ApiResponse[list[TopSkuOut]]:
    return ok(
        AnalyticsService(session, context).top_skus(start_date, end_date, limit, warehouse_id)
    )


@router.get(
    "/sales/top-products", response_model=ApiResponse[list[TopProductOut]], summary="销售 Top SPU"
)
def sales_top_products(
    context: AnalyticsSalesReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
    limit: Limit = 10,
) -> ApiResponse[list[TopProductOut]]:
    return ok(
        AnalyticsService(session, context).top_products(start_date, end_date, limit, warehouse_id)
    )


@router.get(
    "/sales/top-customers",
    response_model=ApiResponse[list[TopCustomerOut]],
    summary="销售 Top 客户",
)
def sales_top_customers(
    context: AnalyticsSalesReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
    limit: Limit = 10,
) -> ApiResponse[list[TopCustomerOut]]:
    return ok(
        AnalyticsService(session, context).top_customers(start_date, end_date, limit, warehouse_id)
    )


@router.get(
    "/purchases/summary", response_model=ApiResponse[PurchaseSummaryOut], summary="采购 KPI"
)
def purchase_summary(
    context: AnalyticsPurchaseReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[PurchaseSummaryOut]:
    return ok(
        AnalyticsService(session, context).purchase_summary(start_date, end_date, warehouse_id)
    )


@router.get(
    "/purchases/trend",
    response_model=ApiResponse[list[PurchaseTrendPoint]],
    summary="采购趋势",
)
def purchase_trend(
    context: AnalyticsPurchaseReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[PurchaseTrendPoint]]:
    return ok(AnalyticsService(session, context).purchase_trend(start_date, end_date, warehouse_id))


@router.get(
    "/purchases/status",
    response_model=ApiResponse[list[StatusCountOut]],
    summary="采购订单状态分布",
)
def purchase_status(
    context: AnalyticsPurchaseReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[StatusCountOut]]:
    return ok(
        AnalyticsService(session, context).purchase_status_distribution(
            start_date, end_date, warehouse_id
        )
    )


@router.get(
    "/purchases/top-suppliers",
    response_model=ApiResponse[list[TopSupplierOut]],
    summary="采购 Top 供应商",
)
def purchase_top_suppliers(
    context: AnalyticsPurchaseReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
    limit: Limit = 10,
) -> ApiResponse[list[TopSupplierOut]]:
    return ok(
        AnalyticsService(session, context).top_suppliers(start_date, end_date, limit, warehouse_id)
    )


@router.get(
    "/inventory/summary",
    response_model=ApiResponse[InventorySummaryOut],
    summary="库存 KPI",
)
def inventory_summary(
    context: AnalyticsInventoryReadContext,
    session: DbSession,
    warehouse_id: WarehouseId = None,
    low_stock_threshold: Threshold = 10,
) -> ApiResponse[InventorySummaryOut]:
    return ok(
        AnalyticsService(session, context).inventory_summary(warehouse_id, low_stock_threshold)
    )


@router.get(
    "/inventory/by-warehouse",
    response_model=ApiResponse[list[WarehouseInventorySummaryOut]],
    summary="库存按仓库分布",
)
def inventory_by_warehouse(
    context: AnalyticsInventoryReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[WarehouseInventorySummaryOut]]:
    return ok(
        AnalyticsService(session, context).inventory_by_warehouse(
            start_date, end_date, warehouse_id
        )
    )


@router.get(
    "/inventory/top-skus",
    response_model=ApiResponse[list[InventorySkuOut]],
    summary="库存 Top SKU",
)
def inventory_top_skus(
    context: AnalyticsInventoryReadContext,
    session: DbSession,
    metric: Annotated[
        str, Query(description="quantity 库存最高 / reserved 预占最高 / available 可用最低")
    ] = "quantity",
    warehouse_id: WarehouseId = None,
    limit: Limit = 10,
) -> ApiResponse[list[InventorySkuOut]]:
    return ok(AnalyticsService(session, context).inventory_top_skus(metric, limit, warehouse_id))


@router.get(
    "/inventory/low-stock",
    response_model=ApiResponse[list[InventorySkuOut]],
    summary="低库存列表",
)
def inventory_low_stock(
    context: AnalyticsInventoryReadContext,
    session: DbSession,
    warehouse_id: WarehouseId = None,
    low_stock_threshold: Threshold = 10,
    limit: Annotated[int, Query(ge=1, le=10000)] = 100,
) -> ApiResponse[list[InventorySkuOut]]:
    return ok(
        AnalyticsService(session, context).low_stock(low_stock_threshold, limit, warehouse_id)
    )


@router.get(
    "/inventory/transactions-trend",
    response_model=ApiResponse[list[TransactionTrendPoint]],
    summary="库存流水趋势",
)
def inventory_transactions_trend(
    context: AnalyticsInventoryReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[TransactionTrendPoint]]:
    return ok(
        AnalyticsService(session, context).inventory_transaction_trend(
            start_date, end_date, warehouse_id
        )
    )


@router.get(
    "/inventory/transactions-by-type",
    response_model=ApiResponse[list[TransactionTypePoint]],
    summary="库存流水类型分布",
)
def inventory_transactions_by_type(
    context: AnalyticsInventoryReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[TransactionTypePoint]]:
    return ok(
        AnalyticsService(session, context).inventory_transaction_types(
            start_date, end_date, warehouse_id
        )
    )


@router.get(
    "/after-sales/summary",
    response_model=ApiResponse[AfterSaleSummaryOut],
    summary="售后 KPI",
)
def after_sale_summary(
    context: AnalyticsAfterSaleReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[AfterSaleSummaryOut]:
    return ok(
        AnalyticsService(session, context).after_sale_summary(start_date, end_date, warehouse_id)
    )


@router.get(
    "/after-sales/trend",
    response_model=ApiResponse[list[AfterSaleTrendPoint]],
    summary="售后趋势",
)
def after_sale_trend(
    context: AnalyticsAfterSaleReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[AfterSaleTrendPoint]]:
    return ok(
        AnalyticsService(session, context).after_sale_trend(start_date, end_date, warehouse_id)
    )


@router.get(
    "/after-sales/types",
    response_model=ApiResponse[list[AfterSaleTypeCountOut]],
    summary="售后类型分布",
)
def after_sale_types(
    context: AnalyticsAfterSaleReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[list[AfterSaleTypeCountOut]]:
    return ok(
        AnalyticsService(session, context).after_sale_type_distribution(
            start_date, end_date, warehouse_id
        )
    )


@router.post(
    "/sales/export-tasks",
    response_model=ApiResponse[AsyncTaskOut],
    summary="异步导出销售按日汇总",
)
def create_sales_export_task(
    context: AnalyticsSalesReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[AsyncTaskOut]:
    payload = ReportExportCreate(
        kind="sales_trend", start_date=start_date, end_date=end_date, warehouse_id=warehouse_id
    )
    return ok(AsyncTaskService(session, context).create_report_export(payload), "已创建导出任务")


@router.post(
    "/purchases/export-tasks",
    response_model=ApiResponse[AsyncTaskOut],
    summary="异步导出采购按日汇总",
)
def create_purchase_export_task(
    context: AnalyticsPurchaseReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> ApiResponse[AsyncTaskOut]:
    payload = ReportExportCreate(
        kind="purchase_trend", start_date=start_date, end_date=end_date, warehouse_id=warehouse_id
    )
    return ok(AsyncTaskService(session, context).create_report_export(payload), "已创建导出任务")


@router.post(
    "/inventory/export-tasks",
    response_model=ApiResponse[AsyncTaskOut],
    summary="异步导出低库存列表",
)
def create_inventory_export_task(
    context: AnalyticsInventoryReadContext,
    session: DbSession,
    warehouse_id: WarehouseId = None,
    low_stock_threshold: Threshold = 10,
) -> ApiResponse[AsyncTaskOut]:
    payload = ReportExportCreate(
        kind="low_stock", warehouse_id=warehouse_id, low_stock_threshold=low_stock_threshold
    )
    return ok(AsyncTaskService(session, context).create_report_export(payload), "已创建导出任务")


@router.get("/sales/trend.csv", summary="导出销售按日汇总 CSV")
def export_sales_trend(
    context: AnalyticsSalesReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> Response:
    filename, content = AnalyticsService(session, context).export_sales_trend_csv(
        start_date, end_date, warehouse_id
    )
    return _csv_response(filename, content)


@router.get("/purchases/trend.csv", summary="导出采购按日汇总 CSV")
def export_purchase_trend(
    context: AnalyticsPurchaseReadContext,
    session: DbSession,
    start_date: StartDate = None,
    end_date: EndDate = None,
    warehouse_id: WarehouseId = None,
) -> Response:
    filename, content = AnalyticsService(session, context).export_purchase_trend_csv(
        start_date, end_date, warehouse_id
    )
    return _csv_response(filename, content)


@router.get("/inventory/low-stock.csv", summary="导出低库存列表 CSV")
def export_low_stock(
    context: AnalyticsInventoryReadContext,
    session: DbSession,
    warehouse_id: WarehouseId = None,
    low_stock_threshold: Threshold = 10,
) -> Response:
    filename, content = AnalyticsService(session, context).export_low_stock_csv(
        low_stock_threshold, warehouse_id
    )
    return _csv_response(filename, content)
