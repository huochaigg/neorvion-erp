from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class OutboundItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_order_item_id: int = Field(gt=0)
    planned_quantity: int = Field(gt=0)


class OutboundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sales_order_id: int = Field(gt=0)
    remark: str | None = Field(default=None, max_length=255)
    items: list[OutboundItemIn] | None = None

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)


class OutboundPickItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    picked_quantity: int = Field(gt=0)


class OutboundPick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 本次增量。不传 finish 时沿用原来的「拣完即结束」，避免旧调用变成可以无限追加。
    items: list[OutboundPickItem] = Field(default_factory=list)
    finish: bool = True


class OutboundPickLineOut(BaseModel):
    id: int
    outbound_order_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    quantity: int
    picked_before: int
    picked_after: int


class OutboundPickOut(BaseModel):
    id: int
    outbound_order_id: int
    outbound_no: str
    outbound_status: str
    picked_at: datetime
    picked_by: int | None
    picked_by_name: str | None
    lines: list[OutboundPickLineOut]


class OutboundItemOut(BaseModel):
    id: int
    sales_order_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict
    planned_quantity: int
    picked_quantity: int
    outbound_quantity: int
    shipped_quantity: int = 0
    remaining_shippable_quantity: int = 0


class OutboundOrderOut(BaseModel):
    id: int
    outbound_no: str
    sales_order_id: int
    sales_order_no: str
    customer_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    remark: str | None
    recipient_name: str | None
    address: str | None
    picked_at: datetime | None
    picked_by: int | None
    confirmed_at: datetime | None
    confirmed_by: int | None
    created_at: datetime
    items: list[OutboundItemOut]
    picks: list[OutboundPickOut] = Field(default_factory=list)


class OutboundListItem(BaseModel):
    id: int
    outbound_no: str
    sales_order_id: int
    sales_order_no: str
    customer_name: str
    warehouse_name: str
    status: str
    sku_count: int
    planned_quantity: int
    picked_quantity: int
    outbound_quantity: int
    created_at: datetime


class OutboundListOut(BaseModel):
    items: list[OutboundListItem]
    total: int
    page: int
    page_size: int
