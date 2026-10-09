from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class ShipmentItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outbound_order_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class ShipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outbound_order_id: int = Field(gt=0)
    carrier_id: int = Field(gt=0)
    tracking_no: str | None = Field(default=None, max_length=64)
    remark: str | None = Field(default=None, max_length=255)
    items: list[ShipmentItemIn] | None = None

    @field_validator("tracking_no", "remark")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _blank(value)


class ShipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carrier_id: int | None = Field(default=None, gt=0)
    tracking_no: str | None = Field(default=None, max_length=64)
    remark: str | None = Field(default=None, max_length=255)
    items: list[ShipmentItemIn] | None = None

    @field_validator("tracking_no", "remark")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _blank(value)


class TrackingEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=128)
    occurred_at: datetime

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("description", "location")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _blank(value)


class ShipmentDeliver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivered_at: datetime | None = None
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("remark")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _blank(value)


class ShipmentItemOut(BaseModel):
    id: int
    outbound_order_item_id: int
    sales_order_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    quantity: int
    outbound_quantity: int
    shipped_before: int


class TrackingEventOut(BaseModel):
    id: int
    status: str
    description: str
    location: str | None
    occurred_at: datetime
    created_by: int | None
    created_at: datetime


class ShipmentOut(BaseModel):
    id: int
    shipment_no: str
    sales_order_id: int
    sales_order_no: str
    outbound_order_id: int
    outbound_no: str
    customer_name: str
    recipient_name: str | None
    address: str | None
    carrier_id: int
    carrier_name: str
    tracking_no: str | None
    status: str
    remark: str | None
    shipped_at: datetime | None
    shipped_by: int | None
    shipped_by_name: str | None
    delivered_at: datetime | None
    created_by: int
    created_at: datetime
    sku_count: int
    total_quantity: int
    items: list[ShipmentItemOut]
    tracking_events: list[TrackingEventOut]


class ShipmentListItem(BaseModel):
    id: int
    shipment_no: str
    sales_order_id: int
    sales_order_no: str
    outbound_order_id: int
    outbound_no: str
    customer_name: str
    carrier_name: str
    tracking_no: str | None
    status: str
    sku_count: int
    total_quantity: int
    shipped_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class ShipmentListOut(BaseModel):
    items: list[ShipmentListItem]
    total: int
    page: int
    page_size: int
