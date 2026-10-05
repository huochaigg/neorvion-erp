from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PurchaseOrderItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class PurchaseOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    expected_arrival_date: date | None = None
    remark: str | None = Field(default=None, max_length=255)
    items: list[PurchaseOrderItemIn] = Field(min_length=1)

    @field_validator("remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def unique_skus(self) -> PurchaseOrderCreate:
        sku_ids = [item.sku_id for item in self.items]
        if len(sku_ids) != len(set(sku_ids)):
            raise ValueError("同一采购单中同一个 SKU 只能出现一行")
        return self


class PurchaseOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: int | None = Field(default=None, gt=0)
    warehouse_id: int | None = Field(default=None, gt=0)
    expected_arrival_date: date | None = None
    remark: str | None = Field(default=None, max_length=255)
    items: list[PurchaseOrderItemIn] | None = Field(default=None, min_length=1)

    @field_validator("remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def require_field(self) -> PurchaseOrderUpdate:
        if not self.model_fields_set:
            raise ValueError("请提供要修改的字段")
        if self.items is not None:
            sku_ids = [item.sku_id for item in self.items]
            if len(sku_ids) != len(set(sku_ids)):
                raise ValueError("同一采购单中同一个 SKU 只能出现一行")
        return self


class PurchaseOrderReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=255)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("请填写驳回原因")
        return text


class PurchaseOrderCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class PurchaseOrderItemOut(BaseModel):
    id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_id: int
    product_name: str
    spec_values: dict
    quantity: int
    unit_price: float | None
    line_amount: float | None
    received_quantity: int
    remark: str | None


class PurchaseOrderListItemOut(BaseModel):
    id: int
    tenant_id: int
    order_no: str
    supplier_id: int
    supplier_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    sku_count: int
    total_quantity: int
    total_amount: float | None
    expected_arrival_date: date | None
    created_by: int
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderListOut(BaseModel):
    items: list[PurchaseOrderListItemOut]
    total: int
    page: int
    page_size: int


class PurchaseOrderDetailOut(PurchaseOrderListItemOut):
    remark: str | None
    submitted_at: datetime | None
    approved_at: datetime | None
    approved_by: int | None
    approved_by_name: str | None
    rejected_at: datetime | None
    rejected_by: int | None
    rejected_by_name: str | None
    reject_reason: str | None
    cancelled_at: datetime | None
    cancelled_by: int | None
    cancelled_by_name: str | None
    cancel_reason: str | None
    items: list[PurchaseOrderItemOut]
