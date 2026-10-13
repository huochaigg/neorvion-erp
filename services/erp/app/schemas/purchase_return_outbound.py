from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class PurchaseReturnOutboundItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_return_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0, description="本次实际退货出库数量")


class PurchaseReturnOutboundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str | None = Field(default=None, max_length=255)
    items: list[PurchaseReturnOutboundItemIn] = Field(min_length=1)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)

    @model_validator(mode="after")
    def unique_items(self) -> "PurchaseReturnOutboundCreate":
        ids = [row.purchase_return_item_id for row in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一出库单中同一个退货明细只能出现一行")
        return self


class PurchaseReturnOutboundItemOut(BaseModel):
    id: int
    purchase_return_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict[str, Any]
    quantity: int = Field(description="本次实际退货出库数量，不是累计已退")
    approved_return_quantity: int
    already_returned_quantity: int
    remaining_return_quantity: int
    inventory_available: int


class PurchaseReturnOutboundOut(BaseModel):
    id: int
    outbound_no: str
    purchase_return_id: int
    purchase_return_no: str
    purchase_order_id: int
    purchase_order_no: str
    supplier_id: int
    supplier_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    remark: str | None
    confirmed_at: datetime | None
    confirmed_by: int | None
    confirmed_by_name: str | None
    created_by: int
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime
    items: list[PurchaseReturnOutboundItemOut] = Field(default_factory=list)


class PurchaseReturnOutboundListItem(BaseModel):
    id: int
    outbound_no: str
    purchase_return_id: int
    purchase_return_no: str
    purchase_order_no: str
    supplier_name: str
    warehouse_name: str
    status: str
    total_quantity: int
    confirmed_at: datetime | None
    created_at: datetime


class PurchaseReturnOutboundListOut(BaseModel):
    items: list[PurchaseReturnOutboundListItem]
    total: int
    page: int
    page_size: int
