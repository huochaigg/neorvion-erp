from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class PurchaseReceiptItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_order_item_id: int = Field(gt=0)
    received_quantity: int = Field(gt=0)


class PurchaseReceiptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_order_id: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=255)
    items: list[PurchaseReceiptItemIn] = Field(min_length=1)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)


class PurchaseReceiptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str | None = Field(default=None, max_length=255)
    items: list[PurchaseReceiptItemIn] = Field(min_length=1)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)


class PurchaseReceiptItemOut(BaseModel):
    id: int
    purchase_order_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    order_quantity: int
    received_before: int
    expected_quantity: int
    received_quantity: int


class PurchaseReceiptOut(BaseModel):
    id: int
    receipt_no: str
    purchase_order_id: int
    purchase_order_no: str
    supplier_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    remark: str | None
    received_by: int | None
    received_by_name: str | None
    received_at: datetime | None
    created_by: int
    created_at: datetime
    sku_count: int
    total_received: int
    items: list[PurchaseReceiptItemOut]


class PurchaseReceiptListItem(BaseModel):
    id: int
    receipt_no: str
    purchase_order_id: int
    purchase_order_no: str
    supplier_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    sku_count: int
    total_received: int
    received_by_name: str | None
    received_at: datetime | None
    created_at: datetime


class PurchaseReceiptListOut(BaseModel):
    items: list[PurchaseReceiptListItem]
    total: int
    page: int
    page_size: int
