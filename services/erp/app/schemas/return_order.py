from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class ReturnOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracking_no: str | None = Field(default=None, max_length=64, description="客户退回物流单号")
    carrier_name: str | None = Field(default=None, max_length=128)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("tracking_no", "carrier_name", "remark")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _blank(value)


class ReturnReceiveItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    received_quantity: int = Field(
        ge=0,
        description="本次收到的数量，会累加到明细已收数量，不能使累计超过预期",
    )
    condition: str = Field(
        min_length=1,
        max_length=16,
        description="GOOD 可入普通库存；DAMAGED / UNSELLABLE 默认不入普通库存",
    )
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("condition")
    @classmethod
    def clean_condition(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)


class ReturnReceiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReturnReceiveItemIn] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> "ReturnReceiveIn":
        ids = [row.item_id for row in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一请求中退货明细不能重复")
        return self


class ReturnOrderItemOut(BaseModel):
    id: int
    after_sale_item_id: int
    sales_order_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict[str, Any]
    expected_quantity: int = Field(description="审核通过后预期客户退回的数量")
    received_quantity: int = Field(description="仓库累计实际收到的退货数量")
    inbound_quantity: int = Field(description="已确认重新进入普通可售库存的数量")
    condition: str
    remark: str | None


class ReturnOrderOut(BaseModel):
    id: int
    return_no: str
    after_sale_order_id: int
    after_sale_no: str
    sales_order_id: int
    sales_order_no: str
    customer_id: int
    customer_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    tracking_no: str | None
    carrier_name: str | None
    remark: str | None
    expected_quantity: int
    received_quantity: int
    inbound_quantity: int
    received_at: datetime | None
    received_by: int | None
    received_by_name: str | None
    confirmed_at: datetime | None
    confirmed_by: int | None
    confirmed_by_name: str | None
    created_at: datetime
    updated_at: datetime
    items: list[ReturnOrderItemOut] = Field(default_factory=list)


class ReturnOrderListItem(BaseModel):
    id: int
    return_no: str
    after_sale_order_id: int
    after_sale_no: str
    sales_order_id: int
    sales_order_no: str
    customer_name: str
    warehouse_name: str
    status: str
    expected_quantity: int
    received_quantity: int
    inbound_quantity: int
    created_at: datetime


class ReturnOrderListOut(BaseModel):
    items: list[ReturnOrderListItem]
    total: int
    page: int
    page_size: int
