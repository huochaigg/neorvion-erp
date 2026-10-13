"""V13 报表 Service：统一口径、补齐日期轴、组合各领域聚合结果。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import StringIO

from sqlalchemy.orm import Session

from app.core.analytics import (
    DEFAULT_LOW_STOCK_THRESHOLD,
    EXPORT_MAX_ROWS,
    clamp_top_limit,
    ensure_export_row_limit,
    iter_dates,
    money,
    money_float,
    resolve_report_range,
)
from app.core.tenant import TenantContext
from app.repositories.analytics_after_sale import AfterSaleAnalyticsRepository
from app.repositories.analytics_inventory import InventoryAnalyticsRepository
from app.repositories.analytics_purchase import PurchaseAnalyticsRepository
from app.repositories.analytics_sales import SalesAnalyticsRepository
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


def _bucket_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _index_by_day(rows: list[tuple], amount_index: int | None = 1) -> dict[str, tuple]:
    return {_bucket_date(row[0]): row for row in rows}


class AnalyticsService:
    def __init__(self, session: Session, context: TenantContext) -> None:
        self.session = session
        self.context = context
        tenant_id = context.tenant_id
        self.sales = SalesAnalyticsRepository(session, tenant_id)
        self.purchases = PurchaseAnalyticsRepository(session, tenant_id)
        self.inventory = InventoryAnalyticsRepository(session, tenant_id)
        self.after_sales = AfterSaleAnalyticsRepository(session, tenant_id)

    def _range(self, start_date: str | None, end_date: str | None):
        return resolve_report_range(start_date, end_date)

    def sales_summary(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> SalesSummaryOut:
        start, end_ex, _, _ = self._range(start_date, end_date)
        gross, order_count = self.sales.sales_amount_and_order_count(start, end_ex, warehouse_id)
        refund = self.sales.success_refund_amount(start, end_ex, warehouse_id)
        completed, cancelled, draft = self.sales.completed_and_cancelled_counts(
            start, end_ex, warehouse_id
        )
        after_counts = self.after_sales.summary_counts(start, end_ex, warehouse_id)
        after_sale_sales_orders = after_counts["after_sale_sales_order_count"]
        aov = money(gross / order_count) if order_count else money(0)
        return_rate = (
            money(Decimal(after_sale_sales_orders) / Decimal(order_count))
            if order_count
            else money(0)
        )
        return SalesSummaryOut(
            order_count=order_count,
            completed_order_count=completed,
            cancelled_order_count=cancelled,
            draft_order_count=draft,
            gross_sales_amount=money_float(gross),
            refund_amount=money_float(refund),
            net_sales_amount=money_float(gross - refund),
            average_order_value=money_float(aov),
            after_sale_order_count=after_counts["after_sale_count"],
            after_sale_sales_order_count=after_sale_sales_orders,
            return_rate=money_float(return_rate),
        )

    def sales_trend(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[SalesTrendPoint]:
        """返回完整日期序列，缺失日补 0，避免折线图断轴。"""
        start, end_ex, start_d, end_d = self._range(start_date, end_date)
        sales_rows = _index_by_day(self.sales.daily_sales_trend(start, end_ex, warehouse_id))
        refund_rows = _index_by_day(self.sales.daily_refund_trend(start, end_ex, warehouse_id))
        points: list[SalesTrendPoint] = []
        for day in iter_dates(start_d, end_d):
            key = day.isoformat()
            sales = sales_rows.get(key)
            refund = refund_rows.get(key)
            points.append(
                SalesTrendPoint(
                    date=key,
                    order_count=int(sales[1]) if sales else 0,
                    sales_amount=money_float(sales[2] if sales else 0),
                    refund_amount=money_float(refund[1] if refund else 0),
                )
            )
        return points

    def sales_status_distribution(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[StatusCountOut]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        counts = self.sales.count_by_status(start, end_ex, warehouse_id)
        return [StatusCountOut(status=status, count=count) for status, count in counts.items()]

    def top_skus(
        self,
        start_date: str | None,
        end_date: str | None,
        limit: int | None = None,
        warehouse_id: int | None = None,
    ) -> list[TopSkuOut]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        rows = self.sales.top_skus(start, end_ex, clamp_top_limit(limit), warehouse_id)
        return [
            TopSkuOut(
                sku_id=int(row[0]),
                sku_code=str(row[1] or ""),
                sku_name=str(row[2] or ""),
                product_id=int(row[3]),
                product_name=str(row[4] or ""),
                spec_values=row[5] or {},
                sales_quantity=int(row[6] or 0),
                sales_amount=money_float(row[7]),
                order_count=int(row[8] or 0),
            )
            for row in rows
        ]

    def top_products(
        self,
        start_date: str | None,
        end_date: str | None,
        limit: int | None = None,
        warehouse_id: int | None = None,
    ) -> list[TopProductOut]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        rows = self.sales.top_products(start, end_ex, clamp_top_limit(limit), warehouse_id)
        return [
            TopProductOut(
                product_id=int(row[0]),
                product_name=str(row[1] or ""),
                sales_quantity=int(row[2] or 0),
                sales_amount=money_float(row[3]),
                sku_count=int(row[4] or 0),
            )
            for row in rows
        ]

    def top_customers(
        self,
        start_date: str | None,
        end_date: str | None,
        limit: int | None = None,
        warehouse_id: int | None = None,
    ) -> list[TopCustomerOut]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        rows = self.sales.top_customers(start, end_ex, clamp_top_limit(limit), warehouse_id)
        refunds = self.sales.success_refund_amount_by_customer(
            start, end_ex, [int(row[0]) for row in rows], warehouse_id
        )
        result: list[TopCustomerOut] = []
        for row in rows:
            cid = int(row[0])
            sales_amount = money(row[3])
            refund_amount = refunds.get(cid, money(0))
            result.append(
                TopCustomerOut(
                    customer_id=cid,
                    customer_name=str(row[1] or ""),
                    order_count=int(row[2] or 0),
                    sales_amount=money_float(sales_amount),
                    refund_amount=money_float(refund_amount),
                    net_sales_amount=money_float(sales_amount - refund_amount),
                )
            )
        return result

    def purchase_summary(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> PurchaseSummaryOut:
        start, end_ex, _, _ = self._range(start_date, end_date)
        amount, count = self.purchases.purchase_amount_and_count(start, end_ex, warehouse_id)
        return_count, return_amount = self.purchases.purchase_return_metrics(
            start, end_ex, warehouse_id
        )
        return PurchaseSummaryOut(
            purchase_order_count=count,
            purchase_amount=money_float(amount),
            received_quantity=self.purchases.received_quantity(start, end_ex, warehouse_id),
            pending_receipt_order_count=self.purchases.pending_receipt_count(warehouse_id),
            purchase_return_order_count=return_count,
            purchase_return_quantity=self.purchases.purchase_return_outbound_quantity(
                start, end_ex, warehouse_id
            ),
            purchase_return_amount=money_float(return_amount),
            supplier_refund_amount=money_float(
                self.purchases.supplier_refund_amount(start, end_ex, warehouse_id)
            ),
        )

    def purchase_trend(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[PurchaseTrendPoint]:
        start, end_ex, start_d, end_d = self._range(start_date, end_date)
        orders = _index_by_day(self.purchases.daily_purchase_trend(start, end_ex, warehouse_id))
        received = _index_by_day(self.purchases.daily_received_trend(start, end_ex, warehouse_id))
        returned = _index_by_day(
            self.purchases.daily_purchase_return_outbound_trend(start, end_ex, warehouse_id)
        )
        points: list[PurchaseTrendPoint] = []
        for day in iter_dates(start_d, end_d):
            key = day.isoformat()
            order_row = orders.get(key)
            recv_row = received.get(key)
            ret_row = returned.get(key)
            points.append(
                PurchaseTrendPoint(
                    date=key,
                    purchase_order_count=int(order_row[1]) if order_row else 0,
                    purchase_amount=money_float(order_row[2] if order_row else 0),
                    received_quantity=int(recv_row[1]) if recv_row else 0,
                    purchase_return_quantity=int(ret_row[1]) if ret_row else 0,
                )
            )
        return points

    def purchase_status_distribution(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[StatusCountOut]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        counts = self.purchases.count_by_status(start, end_ex, warehouse_id)
        return [StatusCountOut(status=status, count=count) for status, count in counts.items()]

    def top_suppliers(
        self,
        start_date: str | None,
        end_date: str | None,
        limit: int | None = None,
        warehouse_id: int | None = None,
    ) -> list[TopSupplierOut]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        rows = self.purchases.top_suppliers(start, end_ex, clamp_top_limit(limit), warehouse_id)
        ids = [int(row[0]) for row in rows]
        received = self.purchases.received_quantity_by_supplier(start, end_ex, ids, warehouse_id)
        returned = self.purchases.purchase_return_quantity_by_supplier(
            start, end_ex, ids, warehouse_id
        )
        return [
            TopSupplierOut(
                supplier_id=int(row[0]),
                supplier_name=str(row[1] or ""),
                purchase_order_count=int(row[2] or 0),
                purchase_amount=money_float(row[3]),
                received_quantity=received.get(int(row[0]), 0),
                purchase_return_quantity=returned.get(int(row[0]), 0),
            )
            for row in rows
        ]

    def inventory_summary(
        self,
        warehouse_id: int | None = None,
        low_stock_threshold: int | None = None,
    ) -> InventorySummaryOut:
        threshold = (
            DEFAULT_LOW_STOCK_THRESHOLD if low_stock_threshold is None else int(low_stock_threshold)
        )
        if threshold < 0:
            threshold = DEFAULT_LOW_STOCK_THRESHOLD
        data = self.inventory.snapshot(warehouse_id, threshold)
        return InventorySummaryOut(**data)

    def inventory_by_warehouse(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[WarehouseInventorySummaryOut]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        rows = self.inventory.by_warehouse(start, end_ex, warehouse_id)
        return [
            WarehouseInventorySummaryOut(
                warehouse_id=int(row[0]),
                warehouse_name=str(row[1] or ""),
                sku_count=int(row[2] or 0),
                quantity=int(row[3] or 0),
                reserved_quantity=int(row[4] or 0),
                available_quantity=int(row[5] or 0),
                inbound_quantity=int(row[6] or 0),
                outbound_quantity=int(row[7] or 0),
                transfer_in_quantity=int(row[8] or 0),
                transfer_out_quantity=int(row[9] or 0),
                stocktake_adjustment_quantity=int(row[10] or 0),
            )
            for row in rows
        ]

    def inventory_top_skus(
        self,
        metric: str = "quantity",
        limit: int | None = None,
        warehouse_id: int | None = None,
    ) -> list[InventorySkuOut]:
        allowed = {"quantity", "reserved", "available"}
        chosen = metric if metric in allowed else "quantity"
        rows = self.inventory.top_skus(
            metric=chosen, limit=clamp_top_limit(limit), warehouse_id=warehouse_id
        )
        return [_inventory_sku(row) for row in rows]

    def low_stock(
        self,
        low_stock_threshold: int | None = None,
        limit: int | None = None,
        warehouse_id: int | None = None,
    ) -> list[InventorySkuOut]:
        threshold = (
            DEFAULT_LOW_STOCK_THRESHOLD if low_stock_threshold is None else int(low_stock_threshold)
        )
        row_limit = EXPORT_MAX_ROWS if limit is None else min(int(limit), EXPORT_MAX_ROWS)
        if row_limit < 1:
            row_limit = 100
        rows = self.inventory.low_stock(threshold, row_limit, warehouse_id)
        return [_inventory_sku(row) for row in rows]

    def inventory_transaction_trend(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[TransactionTrendPoint]:
        start, end_ex, start_d, end_d = self._range(start_date, end_date)
        rows = _index_by_day(self.inventory.daily_transaction_trend(start, end_ex, warehouse_id))
        points: list[TransactionTrendPoint] = []
        for day in iter_dates(start_d, end_d):
            key = day.isoformat()
            row = rows.get(key)
            points.append(
                TransactionTrendPoint(
                    date=key,
                    inbound_quantity=int(row[1]) if row else 0,
                    outbound_quantity=int(row[2]) if row else 0,
                    adjustment_quantity=int(row[3]) if row else 0,
                    transfer_in_quantity=int(row[4]) if row else 0,
                    transfer_out_quantity=int(row[5]) if row else 0,
                )
            )
        return points

    def inventory_transaction_types(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[TransactionTypePoint]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        return [
            TransactionTypePoint(type=type_code, quantity=qty)
            for type_code, qty in self.inventory.transaction_by_type(start, end_ex, warehouse_id)
        ]

    def after_sale_summary(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> AfterSaleSummaryOut:
        start, end_ex, _, _ = self._range(start_date, end_date)
        counts = self.after_sales.summary_counts(start, end_ex, warehouse_id)
        _, valid_orders = self.sales.sales_amount_and_order_count(start, end_ex, warehouse_id)
        distinct = counts["after_sale_sales_order_count"]
        rate = money(Decimal(distinct) / Decimal(valid_orders)) if valid_orders else money(0)
        return AfterSaleSummaryOut(
            after_sale_count=counts["after_sale_count"],
            refund_only_count=counts["refund_only_count"],
            return_only_count=counts["return_only_count"],
            return_and_refund_count=counts["return_and_refund_count"],
            refund_amount=money_float(
                self.after_sales.success_refund_amount(start, end_ex, warehouse_id)
            ),
            return_quantity=counts["return_quantity"],
            after_sale_rate=money_float(rate),
            after_sale_sales_order_count=distinct,
            valid_sales_order_count=valid_orders,
        )

    def after_sale_trend(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[AfterSaleTrendPoint]:
        start, end_ex, start_d, end_d = self._range(start_date, end_date)
        after_rows = _index_by_day(self.after_sales.daily_trend(start, end_ex, warehouse_id))
        refund_rows = _index_by_day(self.sales.daily_refund_trend(start, end_ex, warehouse_id))
        points: list[AfterSaleTrendPoint] = []
        for day in iter_dates(start_d, end_d):
            key = day.isoformat()
            after = after_rows.get(key)
            refund = refund_rows.get(key)
            points.append(
                AfterSaleTrendPoint(
                    date=key,
                    after_sale_count=int(after[1]) if after else 0,
                    return_quantity=int(after[2]) if after else 0,
                    refund_amount=money_float(refund[1] if refund else 0),
                )
            )
        return points

    def after_sale_type_distribution(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> list[AfterSaleTypeCountOut]:
        start, end_ex, _, _ = self._range(start_date, end_date)
        return [
            AfterSaleTypeCountOut(type=type_code, count=count)
            for type_code, count in self.after_sales.type_counts(start, end_ex, warehouse_id)
        ]

    def pending(
        self,
        warehouse_id: int | None = None,
        low_stock_threshold: int | None = None,
    ) -> PendingCountsOut:
        threshold = (
            DEFAULT_LOW_STOCK_THRESHOLD if low_stock_threshold is None else int(low_stock_threshold)
        )
        pending_confirm, waiting_outbound = self.sales.pending_counts(warehouse_id)
        pending_after, waiting_refund = self.after_sales.pending_counts(warehouse_id)
        snapshot = self.inventory.snapshot(warehouse_id, threshold)
        return PendingCountsOut(
            pending_confirmation_order_count=pending_confirm,
            waiting_outbound_order_count=waiting_outbound,
            pending_receipt_order_count=self.purchases.pending_receipt_count(warehouse_id),
            pending_after_sale_count=pending_after,
            waiting_refund_after_sale_count=waiting_refund,
            pending_purchase_return_count=self.purchases.pending_purchase_return_count(
                warehouse_id
            ),
            low_stock_sku_count=snapshot["low_stock_sku_count"],
            low_stock_threshold=threshold,
        )

    def overview(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
        low_stock_threshold: int | None = None,
    ) -> OverviewOut:
        return OverviewOut(
            sales=self.sales_summary(start_date, end_date, warehouse_id),
            purchases=self.purchase_summary(start_date, end_date, warehouse_id),
            inventory=self.inventory_summary(warehouse_id, low_stock_threshold),
            after_sales=self.after_sale_summary(start_date, end_date, warehouse_id),
            pending=self.pending(warehouse_id, low_stock_threshold),
        )

    def export_sales_trend_csv(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> tuple[str, str]:
        rows = self.sales_trend(start_date, end_date, warehouse_id)
        ensure_export_row_limit(len(rows))
        return _csv(
            ["日期", "有效订单数", "销售金额", "成功退款金额"],
            [[p.date, p.order_count, p.sales_amount, p.refund_amount] for p in rows],
            "sales-trend.csv",
        )

    def export_purchase_trend_csv(
        self,
        start_date: str | None,
        end_date: str | None,
        warehouse_id: int | None = None,
    ) -> tuple[str, str]:
        rows = self.purchase_trend(start_date, end_date, warehouse_id)
        ensure_export_row_limit(len(rows))
        return _csv(
            ["日期", "有效采购单数", "采购金额", "收货数量", "采购退货出库数量"],
            [
                [
                    p.date,
                    p.purchase_order_count,
                    p.purchase_amount,
                    p.received_quantity,
                    p.purchase_return_quantity,
                ]
                for p in rows
            ],
            "purchase-trend.csv",
        )

    def export_low_stock_csv(
        self,
        low_stock_threshold: int | None = None,
        warehouse_id: int | None = None,
    ) -> tuple[str, str]:
        rows = self.low_stock(low_stock_threshold, EXPORT_MAX_ROWS, warehouse_id)
        ensure_export_row_limit(len(rows))
        return _csv(
            ["SKU编码", "SKU名称", "商品", "仓库", "实际库存", "预占", "可用库存"],
            [
                [
                    p.sku_code,
                    p.sku_name,
                    p.product_name,
                    p.warehouse_name,
                    p.quantity,
                    p.reserved_quantity,
                    p.available_quantity,
                ]
                for p in rows
            ],
            "low-stock.csv",
        )


def _inventory_sku(row: tuple) -> InventorySkuOut:
    return InventorySkuOut(
        sku_id=int(row[0]),
        sku_code=str(row[1] or ""),
        sku_name=str(row[2] or ""),
        product_name=str(row[3] or ""),
        warehouse_id=int(row[4]),
        warehouse_name=str(row[5] or ""),
        quantity=int(row[6] or 0),
        reserved_quantity=int(row[7] or 0),
        available_quantity=int(row[8] or 0),
    )


def _csv_cell(value: object) -> object:
    """防止 CSV Formula Injection：Excel 打开时不要执行用户输入公式。"""
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return f"'{value}"
    return value


def _csv(headers: list[str], rows: list[list[object]], filename: str) -> tuple[str, str]:
    import csv

    buffer = StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows([[_csv_cell(cell) for cell in row] for row in rows])
    return filename, buffer.getvalue()
