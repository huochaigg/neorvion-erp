from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.outbound import OutboundPickOut


class SalesOrderItemIn(BaseModel):
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


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class SalesOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    source: str | None = Field(default=None, max_length=16)
    external_order_no: str | None = Field(default=None, max_length=64)
    currency_code: str | None = Field(default=None, max_length=3)
    recipient_name: str | None = Field(default=None, max_length=128)
    recipient_phone: str | None = Field(default=None, max_length=32)
    country_code: str | None = Field(default=None, max_length=2)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=255)
    items: list[SalesOrderItemIn] = Field(min_length=1)

    @field_validator(
        "external_order_no",
        "recipient_name",
        "recipient_phone",
        "province",
        "city",
        "address",
        "remark",
    )
    @classmethod
    def empty_text(cls, value: str | None) -> str | None:
        return _empty_to_none(value)

    @field_validator("source", "currency_code", "country_code")
    @classmethod
    def normalize_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper()
        return text or None

    @model_validator(mode="after")
    def unique_skus(self) -> SalesOrderCreate:
        sku_ids = [item.sku_id for item in self.items]
        if len(sku_ids) != len(set(sku_ids)):
            raise ValueError("同一销售订单中同一个 SKU 只能出现一行")
        return self


class SalesOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int | None = Field(default=None, gt=0)
    warehouse_id: int | None = Field(default=None, gt=0)
    source: str | None = Field(default=None, max_length=16)
    external_order_no: str | None = Field(default=None, max_length=64)
    currency_code: str | None = Field(default=None, max_length=3)
    recipient_name: str | None = Field(default=None, max_length=128)
    recipient_phone: str | None = Field(default=None, max_length=32)
    country_code: str | None = Field(default=None, max_length=2)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=255)
    items: list[SalesOrderItemIn] | None = Field(default=None, min_length=1)

    @field_validator(
        "external_order_no",
        "recipient_name",
        "recipient_phone",
        "province",
        "city",
        "address",
        "remark",
    )
    @classmethod
    def empty_text(cls, value: str | None) -> str | None:
        return _empty_to_none(value)

    @field_validator("source", "currency_code", "country_code")
    @classmethod
    def normalize_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper()
        return text or None

    @model_validator(mode="after")
    def require_field(self) -> SalesOrderUpdate:
        if not self.model_fields_set:
            raise ValueError("请提供要修改的字段")
        if self.items is not None:
            sku_ids = [item.sku_id for item in self.items]
            if len(sku_ids) != len(set(sku_ids)):
                raise ValueError("同一销售订单中同一个 SKU 只能出现一行")
        return self


class SalesOrderCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def empty_text(cls, value: str | None) -> str | None:
        return _empty_to_none(value)


class SalesOrderItemOut(BaseModel):
    id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_id: int
    product_name: str
    spec_values: dict[str, Any]
    quantity: int
    unit_price: float | None
    line_amount: float | None
    reserved_quantity: int
    shipped_quantity: int
    remark: str | None
    # 履约仓库上的实时账面，只给页面提示。不是订单历史，确认时以后端再查一次为准。
    current_quantity: int | None
    current_reserved_quantity: int | None
    current_available_quantity: int | None


class SalesOrderListItemOut(BaseModel):
    id: int
    tenant_id: int
    order_no: str
    customer_id: int
    customer_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    source: str
    external_order_no: str | None
    currency_code: str
    sku_count: int
    total_quantity: int
    total_amount: float | None
    created_by: int
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class SalesOrderListOut(BaseModel):
    items: list[SalesOrderListItemOut]
    total: int
    page: int
    page_size: int


class SalesOrderDetailOut(SalesOrderListItemOut):
    recipient_name: str | None
    recipient_phone: str | None
    country_code: str | None
    province: str | None
    city: str | None
    address: str | None
    remark: str | None
    submitted_at: datetime | None
    confirmed_at: datetime | None
    confirmed_by: int | None
    confirmed_by_name: str | None
    cancelled_at: datetime | None
    cancelled_by: int | None
    cancelled_by_name: str | None
    cancel_reason: str | None
    items: list[SalesOrderItemOut]
    picks: list[OutboundPickOut] = Field(default_factory=list)
