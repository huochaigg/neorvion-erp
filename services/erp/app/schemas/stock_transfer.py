from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class StockTransferItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class StockTransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_warehouse_id: int = Field(gt=0)
    target_warehouse_id: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=255)
    items: list[StockTransferItemIn] = Field(min_length=1)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)

    @model_validator(mode="after")
    def unique_skus(self) -> "StockTransferCreate":
        ids = [row.sku_id for row in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一调拨单不能重复添加同一 SKU")
        return self


class StockTransferUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_warehouse_id: int = Field(gt=0)
    target_warehouse_id: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=255)
    items: list[StockTransferItemIn] = Field(min_length=1)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)

    @model_validator(mode="after")
    def unique_skus(self) -> "StockTransferUpdate":
        ids = [row.sku_id for row in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一调拨单不能重复添加同一 SKU")
        return self


class StockTransferItemOut(BaseModel):
    id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict[str, object]
    quantity: int
    outbound_quantity: int
    received_quantity: int
    source_quantity: int | None = None
    source_reserved_quantity: int | None = None
    source_available_quantity: int | None = None


class StockTransferOut(BaseModel):
    id: int
    transfer_no: str
    source_warehouse_id: int
    source_warehouse_name: str
    target_warehouse_id: int
    target_warehouse_name: str
    status: str
    remark: str | None
    sku_count: int
    total_quantity: int
    created_by: int
    created_by_name: str | None
    submitted_at: datetime | None
    outbound_at: datetime | None
    outbound_by: int | None
    outbound_by_name: str | None
    received_at: datetime | None
    received_by: int | None
    received_by_name: str | None
    cancelled_at: datetime | None
    cancelled_by: int | None
    created_at: datetime
    updated_at: datetime
    items: list[StockTransferItemOut]


class StockTransferListItem(BaseModel):
    id: int
    transfer_no: str
    source_warehouse_id: int
    source_warehouse_name: str
    target_warehouse_id: int
    target_warehouse_name: str
    status: str
    sku_count: int
    total_quantity: int
    created_by_name: str | None
    created_at: datetime


class StockTransferListOut(BaseModel):
    items: list[StockTransferListItem]
    total: int
    page: int
    page_size: int
