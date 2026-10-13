from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class AfterSaleItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_order_item_id: int = Field(gt=0, description="原销售订单明细 id")
    return_quantity: int = Field(
        default=0,
        ge=0,
        description="本次申请退回的商品数量，不代表历史累计退货数量",
    )
    requested_refund_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="本次申请退款金额，单位和币种沿用原销售订单",
    )
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return _blank(value)


class AfterSaleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_order_id: int = Field(gt=0)
    type: str = Field(
        min_length=1,
        max_length=24,
        description="REFUND_ONLY 仅退款；RETURN_AND_REFUND 退货后退款；RETURN_ONLY 只退货",
    )
    reason: str = Field(min_length=1, max_length=255, description="申请原因")
    description: str | None = Field(default=None, max_length=512)
    items: list[AfterSaleItemIn] = Field(min_length=1)

    @field_validator("type")
    @classmethod
    def clean_type(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("申请原因不能为空")
        return text

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return _blank(value)

    @model_validator(mode="after")
    def unique_items(self) -> "AfterSaleCreate":
        ids = [row.sales_order_item_id for row in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一售后单中同一个销售明细只能出现一行")
        return self


class AfterSaleApproveItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    approved_return_quantity: int = Field(
        ge=0,
        description="审核最终允许客户退回的数量，可能小于申请退货数量",
    )
    approved_refund_amount: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="审核最终同意的本明细退款金额",
    )


class AfterSaleApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: int | None = Field(
        default=None,
        gt=0,
        description="退货入库仓库。不填则使用原销售订单履约仓",
    )
    items: list[AfterSaleApproveItemIn] = Field(default_factory=list)


class AfterSaleReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=255, description="拒绝原因")

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("拒绝原因不能为空")
        return text


class AfterSaleItemOut(BaseModel):
    id: int
    sales_order_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict[str, Any]
    original_quantity: int = Field(description="原销售订单该 SKU 的购买数量快照")
    outbound_quantity: int = Field(description="原销售明细当前累计正式出库数量")
    return_quantity: int
    approved_return_quantity: int | None
    requested_refund_amount: float
    approved_refund_amount: float | None
    reason: str | None


class AfterSaleOut(BaseModel):
    id: int
    after_sale_no: str
    sales_order_id: int
    sales_order_no: str
    customer_id: int
    customer_name: str
    type: str
    status: str
    reason: str
    description: str | None
    currency_code: str
    requested_refund_amount: float
    approved_refund_amount: float | None
    refund_status: str
    return_quantity: int
    requested_by: int
    requested_by_name: str | None
    approved_by: int | None
    approved_by_name: str | None
    approved_at: datetime | None
    rejected_by: int | None
    rejected_at: datetime | None
    reject_reason: str | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancelled_by: int | None
    created_at: datetime
    updated_at: datetime
    return_order_id: int | None = None
    items: list[AfterSaleItemOut] = Field(default_factory=list)


class AfterSaleListItem(BaseModel):
    id: int
    after_sale_no: str
    sales_order_id: int
    sales_order_no: str
    customer_id: int
    customer_name: str
    type: str
    status: str
    refund_status: str
    return_quantity: int
    requested_refund_amount: float
    approved_refund_amount: float | None
    requested_by_name: str | None
    created_at: datetime


class AfterSaleListOut(BaseModel):
    items: list[AfterSaleListItem]
    total: int
    page: int
    page_size: int


class AfterSalePreviewItem(BaseModel):
    sales_order_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict[str, Any]
    original_quantity: int
    outbound_quantity: int = Field(description="已经正式出库、可作为可退上限的数量")
    occupied_return_quantity: int = Field(
        description="有效未取消/未拒绝售后已占用的退货数量",
    )
    returnable_quantity: int = Field(description="当前还能再申请退货的数量")
    unit_price: float | None
    occupied_refund_amount: float
    refundable_amount: float = Field(description="当前还能再申请的退款金额")


class AfterSalePreviewOut(BaseModel):
    sales_order_id: int
    sales_order_no: str
    customer_id: int
    customer_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    currency_code: str
    total_amount: float | None
    eligible: bool
    items: list[AfterSalePreviewItem]
