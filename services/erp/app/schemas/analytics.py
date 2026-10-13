"""V13 报表 API Schema。金额字段在 JSON 中沿用 float，计算过程使用 Decimal。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DateRangeQuery(BaseModel):
    start_date: str | None = Field(default=None, description="开始日期 YYYY-MM-DD，含当天 00:00:00")
    end_date: str | None = Field(
        default=None, description="结束日期 YYYY-MM-DD，统计到当天结束（次日 00:00:00 不含）"
    )


class SalesSummaryOut(BaseModel):
    order_count: int = Field(
        ...,
        description="有效销售订单数。有效 = 排除 DRAFT、CANCELLED；按 created_at 落入统计区间",
    )
    completed_order_count: int = Field(..., description="统计区间内状态为 COMPLETED 的销售订单数")
    cancelled_order_count: int = Field(
        ...,
        description="统计区间内 CANCELLED 订单数。取消单不计入 order_count 与销售额",
    )
    draft_order_count: int = Field(..., description="统计区间内 DRAFT 订单数，不计入销售额")
    gross_sales_amount: float = Field(
        ...,
        description="销售金额合计。SUM(明细单价×数量)，仅有效销售订单；单价为空按 0",
    )
    refund_amount: float = Field(
        ...,
        description="成功退款金额。只统计 SUCCESS，时间取 refunded_at，空则 created_at",
    )
    net_sales_amount: float = Field(
        ...,
        description="净销售额 = gross_sales_amount − refund_amount。PENDING / FAILED 退款不扣减",
    )
    average_order_value: float = Field(
        ...,
        description="平均订单金额 = gross_sales_amount ÷ order_count。有效订单数为 0 时返回 0",
    )
    after_sale_order_count: int = Field(
        ...,
        description="统计区间内有效售后单数量。有效售后排除 REJECTED、CANCELLED",
    )
    after_sale_sales_order_count: int = Field(
        ...,
        description="发生有效售后的销售订单去重数，COUNT(DISTINCT sales_order_id)，用于售后率分子",
    )
    return_rate: float = Field(
        ...,
        description="售后率 = 发生有效售后的销售订单去重数 ÷ 有效销售订单数。分母为 0 时返回 0",
    )


class SalesTrendPoint(BaseModel):
    date: str = Field(..., description="自然日 YYYY-MM-DD，缺失日已补 0")
    order_count: int = Field(..., description="当日有效销售订单数")
    sales_amount: float = Field(..., description="当日有效销售订单金额合计")
    refund_amount: float = Field(..., description="当日成功退款金额合计")


class StatusCountOut(BaseModel):
    status: str
    count: int = Field(..., description="该状态在统计区间内的单据数量，按 created_at")


class TopSkuOut(BaseModel):
    sku_id: int
    sku_code: str
    sku_name: str
    product_id: int
    product_name: str
    spec_values: dict = Field(default_factory=dict)
    sales_quantity: int = Field(..., description="有效销售订单中该 SKU 的购买数量合计")
    sales_amount: float = Field(
        ..., description="有效销售订单中该 SKU 的 unit_price × quantity 合计"
    )
    order_count: int = Field(..., description="包含该 SKU 的有效销售订单数")


class TopProductOut(BaseModel):
    product_id: int
    product_name: str
    sales_quantity: int = Field(..., description="该 SPU 下全部 SKU 的有效销量合计")
    sales_amount: float = Field(..., description="该 SPU 下全部 SKU 的有效销售额合计")
    sku_count: int = Field(..., description="统计期内有销量的 SKU 种数")


class TopCustomerOut(BaseModel):
    customer_id: int
    customer_name: str
    order_count: int = Field(..., description="该客户有效销售订单数")
    sales_amount: float = Field(..., description="该客户有效销售金额")
    refund_amount: float = Field(..., description="该客户成功退款金额")
    net_sales_amount: float = Field(..., description="该客户净销售额 = 销售金额 − 成功退款")


class PurchaseSummaryOut(BaseModel):
    purchase_order_count: int = Field(
        ...,
        description="有效采购单数。有效 = 排除 DRAFT、REJECTED、CANCELLED；按 created_at",
    )
    purchase_amount: float = Field(
        ...,
        description="采购金额。SUM(明细 unit_price × quantity)，仅有效采购单；unit_price 为空按 0",
    )
    received_quantity: int = Field(
        ...,
        description="确认收货实收合计。时间取 received_at，空则 created_at；仅 CONFIRMED",
    )
    pending_receipt_order_count: int = Field(
        ...,
        description="当前待收货采购单数（待收货+部分收货），快照口径，不受时间筛选",
    )
    purchase_return_order_count: int = Field(
        ...,
        description="统计区间内有效采购退货单数。有效 = 排除 DRAFT、REJECTED、CANCELLED",
    )
    purchase_return_quantity: int = Field(
        ...,
        description="采购退货出库数量。按流水 PURCHASE_RETURN_OUTBOUND 的绝对值",
    )
    purchase_return_amount: float = Field(
        ...,
        description="统计区间内有效采购退货单的申请退款金额合计 requested_refund_amount",
    )
    supplier_refund_amount: float = Field(
        ...,
        description="成功供应商退款金额。只统计 SupplierRefundRecord.status=SUCCESS",
    )


class PurchaseTrendPoint(BaseModel):
    date: str = Field(..., description="自然日 YYYY-MM-DD，缺失日已补 0")
    purchase_order_count: int = Field(..., description="当日有效采购单数")
    purchase_amount: float = Field(..., description="当日有效采购金额")
    received_quantity: int = Field(..., description="当日确认收货实收数量")
    purchase_return_quantity: int = Field(..., description="当日采购退货出库数量")


class TopSupplierOut(BaseModel):
    supplier_id: int
    supplier_name: str
    purchase_order_count: int = Field(..., description="该供应商有效采购单数")
    purchase_amount: float = Field(..., description="该供应商有效采购金额")
    received_quantity: int = Field(..., description="该供应商在统计期内确认收货数量")
    purchase_return_quantity: int = Field(..., description="该供应商在统计期内采购退货出库数量")


class InventorySummaryOut(BaseModel):
    inventory_record_count: int = Field(..., description="库存台账行数（租户 + 仓库 + SKU）")
    sku_count: int = Field(..., description="有库存台账的 SKU 去重数")
    warehouse_count: int = Field(..., description="有库存台账的仓库去重数")
    total_quantity: int = Field(..., description="实际库存合计 SUM(Inventory.quantity)")
    total_reserved_quantity: int = Field(
        ..., description="预占库存合计 SUM(Inventory.reserved_quantity)"
    )
    total_available_quantity: int = Field(
        ...,
        description="可用库存合计 SUM(quantity − reserved_quantity)，不落库第三份字段",
    )
    zero_stock_sku_count: int = Field(
        ...,
        description="零可用库存行数。available == 0；账面有货但全部预占也算零可用",
    )
    low_stock_sku_count: int = Field(
        ...,
        description="低库存行数。定义：available_quantity <= low_stock_threshold。默认阈值 10",
    )
    low_stock_threshold: int = Field(..., description="本次查询使用的低库存阈值")


class WarehouseInventorySummaryOut(BaseModel):
    warehouse_id: int
    warehouse_name: str
    sku_count: int = Field(..., description="该仓有台账的 SKU 数")
    quantity: int = Field(..., description="该仓实际库存合计")
    reserved_quantity: int = Field(..., description="该仓预占合计")
    available_quantity: int = Field(..., description="该仓可用库存合计")
    inbound_quantity: int = Field(..., description="统计期内该仓入库类流水数量（正数合计）")
    outbound_quantity: int = Field(..., description="统计期内该仓出库类流水数量（绝对值合计）")
    transfer_in_quantity: int = Field(..., description="统计期内调拨入数量")
    transfer_out_quantity: int = Field(..., description="统计期内调拨出数量")
    stocktake_adjustment_quantity: int = Field(
        ...,
        description="统计期内盘点调整 change_quantity 合计，可正可负",
    )


class InventorySkuOut(BaseModel):
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    warehouse_id: int
    warehouse_name: str
    quantity: int = Field(..., description="该仓该 SKU 实际库存")
    reserved_quantity: int = Field(..., description="该仓该 SKU 预占")
    available_quantity: int = Field(..., description="可用 = quantity − reserved_quantity")


class TransactionTrendPoint(BaseModel):
    date: str = Field(..., description="自然日 YYYY-MM-DD，缺失日已补 0")
    inbound_quantity: int = Field(
        ..., description="当日入库类数量：INBOUND / INITIALIZE / ADJUST_IN / RETURN_INBOUND"
    )
    outbound_quantity: int = Field(
        ...,
        description="当日出库类数量绝对值：OUTBOUND / ADJUST_OUT / PURCHASE_RETURN_OUTBOUND",
    )
    adjustment_quantity: int = Field(..., description="当日盘点调整 change_quantity 合计")
    transfer_in_quantity: int = Field(..., description="当日调拨入")
    transfer_out_quantity: int = Field(..., description="当日调拨出")


class TransactionTypePoint(BaseModel):
    type: str = Field(..., description="InventoryTransaction.type 当前枚举值")
    quantity: int = Field(..., description="该类型 change_quantity 合计；出库类为负数")


class AfterSaleSummaryOut(BaseModel):
    after_sale_count: int = Field(..., description="有效售后单数量，排除 REJECTED、CANCELLED")
    refund_only_count: int = Field(..., description="类型为 REFUND_ONLY 的有效售后单数")
    return_only_count: int = Field(..., description="类型为 RETURN_ONLY 的有效售后单数")
    return_and_refund_count: int = Field(..., description="类型为 RETURN_AND_REFUND 的有效售后单数")
    refund_amount: float = Field(..., description="成功退款金额，口径同销售 refund_amount")
    return_quantity: int = Field(
        ...,
        description="有效售后退货数量。优先批准数量，空则申请退货数量",
    )
    after_sale_rate: float = Field(
        ...,
        description="售后率 = 去重销售订单数 ÷ 有效销售订单数，不是售后单数 ÷ 订单数",
    )
    after_sale_sales_order_count: int = Field(..., description="发生有效售后的销售订单去重数")
    valid_sales_order_count: int = Field(..., description="同期有效销售订单数，售后率分母")


class AfterSaleTrendPoint(BaseModel):
    date: str = Field(..., description="自然日 YYYY-MM-DD，缺失日已补 0")
    after_sale_count: int = Field(..., description="当日有效售后单数")
    return_quantity: int = Field(..., description="当日有效售后退货数量")
    refund_amount: float = Field(..., description="当日成功退款金额")


class AfterSaleTypeCountOut(BaseModel):
    type: str
    count: int = Field(..., description="该售后类型的有效售后单数")


class PendingCountsOut(BaseModel):
    pending_confirmation_order_count: int = Field(..., description="当前待确认销售订单数，快照")
    waiting_outbound_order_count: int = Field(..., description="当前待出库销售订单数，快照")
    pending_receipt_order_count: int = Field(..., description="当前待收货采购单数，快照")
    pending_after_sale_count: int = Field(..., description="当前待审核售后单数，快照")
    waiting_refund_after_sale_count: int = Field(..., description="当前待退款售后单数，快照")
    pending_purchase_return_count: int = Field(
        ..., description="当前待处理采购退货单数（待审核/待出库/部分退货）"
    )
    low_stock_sku_count: int = Field(
        ..., description="当前低库存台账行数，阈值见 low_stock_threshold"
    )
    low_stock_threshold: int


class OverviewOut(BaseModel):
    sales: SalesSummaryOut
    purchases: PurchaseSummaryOut
    inventory: InventorySummaryOut
    after_sales: AfterSaleSummaryOut
    pending: PendingCountsOut
