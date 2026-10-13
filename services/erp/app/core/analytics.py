"""V13 报表公共口径：时间边界、有效状态、金额零值。

统计时区：与业务库一致，使用 naive 本地墙钟时间（datetime.now()），不是 UTC。
日期边界：[start_date 当天 00:00:00, end_date 次日 00:00:00)。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import AppError
from app.models.after_sale import AfterSaleStatus
from app.models.purchase import PurchaseOrderStatus
from app.models.purchase_return import PurchaseReturnStatus
from app.models.sales_order import SalesOrderStatus

DATE_FORMAT = "%Y-%m-%d"
MAX_RANGE_DAYS = 366
EXPORT_MAX_ROWS = 10_000
DEFAULT_LOW_STOCK_THRESHOLD = 10
DEFAULT_TOP_LIMIT = 10
MAX_TOP_LIMIT = 20

MONEY_ZERO = Decimal("0.00")
MONEY_QUANT = Decimal("0.01")

# 有效销售订单：已进入履约链路。草稿未提交、取消单不计入销售额与销量。
SALES_INVALID_STATUSES: frozenset[str] = frozenset(
    {
        SalesOrderStatus.DRAFT.value,
        SalesOrderStatus.CANCELLED.value,
    }
)

# 有效采购单：已提交审核及之后。草稿、驳回、取消不计入采购额。
PURCHASE_INVALID_STATUSES: frozenset[str] = frozenset(
    {
        PurchaseOrderStatus.DRAFT.value,
        PurchaseOrderStatus.REJECTED.value,
        PurchaseOrderStatus.CANCELLED.value,
    }
)

# 有效售后：占用可退或已完成。拒绝 / 取消不计入售后率分子。
AFTER_SALE_INVALID_STATUSES: frozenset[str] = frozenset(
    {
        AfterSaleStatus.REJECTED.value,
        AfterSaleStatus.CANCELLED.value,
    }
)

# 有效采购退货：不含草稿 / 驳回 / 取消。
PURCHASE_RETURN_INVALID_STATUSES: frozenset[str] = frozenset(
    {
        PurchaseReturnStatus.DRAFT.value,
        PurchaseReturnStatus.REJECTED.value,
        PurchaseReturnStatus.CANCELLED.value,
    }
)

SALES_PENDING_CONFIRMATION = SalesOrderStatus.PENDING_CONFIRMATION.value
SALES_WAITING_OUTBOUND = SalesOrderStatus.WAITING_OUTBOUND.value
SALES_COMPLETED = SalesOrderStatus.COMPLETED.value
SALES_CANCELLED = SalesOrderStatus.CANCELLED.value

PURCHASE_WAITING_RECEIPT = PurchaseOrderStatus.WAITING_RECEIPT.value
PURCHASE_PARTIALLY_RECEIVED = PurchaseOrderStatus.PARTIALLY_RECEIVED.value

AFTER_SALE_PENDING_APPROVAL = AfterSaleStatus.PENDING_APPROVAL.value
AFTER_SALE_WAITING_REFUND = AfterSaleStatus.WAITING_REFUND.value

PURCHASE_RETURN_PENDING_STATUSES: frozenset[str] = frozenset(
    {
        PurchaseReturnStatus.PENDING_APPROVAL.value,
        PurchaseReturnStatus.WAITING_OUTBOUND.value,
        PurchaseReturnStatus.PARTIALLY_RETURNED.value,
    }
)


def money(value: Decimal | int | float | str | None) -> Decimal:
    """聚合金额统一量化到分。空值当 0，避免前端判断 None。"""
    if value is None:
        return MONEY_ZERO
    quantized = Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    return quantized


def money_float(value: Decimal | int | float | str | None) -> float:
    """API 输出沿用现有订单金额的 float JSON 约定；计算过程必须走 Decimal。"""
    return float(money(value))


def int_or_zero(value: int | None) -> int:
    return int(value or 0)


def parse_report_date(value: str | None, *, field: str) -> date | None:
    if value is None or value.strip() == "":
        return None
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT).date()
    except ValueError as exc:
        raise AppError(
            f"{field} 必须是 YYYY-MM-DD",
            code=40600,
            status_code=400,
            data={"error": "INVALID_DATE", "field": field},
        ) from exc


def default_report_range(today: date | None = None) -> tuple[date, date]:
    """未传日期时默认最近 30 天（含今天）。"""
    end = today or datetime.now().date()
    start = end - timedelta(days=29)
    return start, end


def resolve_report_range(
    start_date: str | None,
    end_date: str | None,
    *,
    today: date | None = None,
) -> tuple[datetime, datetime, date, date]:
    """把 YYYY-MM-DD 转成半开区间 [start, end_exclusive)。

    统计口径：
    时间范围：按业务库 naive 本地日期，不是 UTC。
    返回值：start_dt, end_exclusive_dt, start_date, end_date（含两端自然日）。
    """
    start = parse_report_date(start_date, field="start_date")
    end = parse_report_date(end_date, field="end_date")
    if start is None and end is None:
        start, end = default_report_range(today)
    elif start is None or end is None:
        raise AppError(
            "start_date 与 end_date 必须同时提供",
            code=40600,
            status_code=400,
            data={"error": "DATE_RANGE_INCOMPLETE"},
        )
    if start > end:
        raise AppError(
            "开始日期不能晚于结束日期",
            code=40600,
            status_code=400,
            data={"error": "START_AFTER_END"},
        )
    span = (end - start).days + 1
    if span > MAX_RANGE_DAYS:
        raise AppError(
            f"统计区间最多 {MAX_RANGE_DAYS} 天",
            code=40600,
            status_code=400,
            data={"error": "DATE_RANGE_TOO_LONG", "max_days": MAX_RANGE_DAYS},
        )
    start_dt = datetime.combine(start, datetime.min.time())
    end_exclusive = datetime.combine(end + timedelta(days=1), datetime.min.time())
    return start_dt, end_exclusive, start, end


def iter_dates(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def clamp_top_limit(limit: int | None) -> int:
    value = DEFAULT_TOP_LIMIT if limit is None else int(limit)
    if value < 1:
        return DEFAULT_TOP_LIMIT
    return min(value, MAX_TOP_LIMIT)


def ensure_export_row_limit(row_count: int) -> None:
    if row_count > EXPORT_MAX_ROWS:
        raise AppError(
            f"导出超过 {EXPORT_MAX_ROWS} 行上限，请缩小时间范围",
            code=40602,
            status_code=400,
            data={"error": "EXPORT_TOO_LARGE", "max_rows": EXPORT_MAX_ROWS, "row_count": row_count},
        )
