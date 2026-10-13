from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class StocktakeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: int = Field(gt=0)
    scope: str = Field(min_length=1, max_length=16)
    sku_ids: list[int] = Field(default_factory=list)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("scope")
    @classmethod
    def clean_scope(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)

    @field_validator("sku_ids")
    @classmethod
    def unique_sku_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class StocktakeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remark: str | None = Field(default=None, max_length=255)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)


class StocktakeItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counted_quantity: int = Field(ge=0)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)


class StocktakeItemBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    counted_quantity: int = Field(ge=0)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("remark")
    @classmethod
    def clean_remark(cls, value: str | None) -> str | None:
        return _blank(value)


class StocktakeItemsSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StocktakeItemBatchIn] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_items(self) -> "StocktakeItemsSave":
        ids = [row.item_id for row in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一请求不能重复提交同一条盘点明细")
        return self


class StocktakeItemOut(BaseModel):
    id: int
    inventory_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict[str, object]
    system_quantity: int
    system_reserved_quantity: int
    system_available_quantity: int
    counted_quantity: int | None
    difference_quantity: int | None
    remark: str | None


class StocktakeOut(BaseModel):
    id: int
    stocktake_no: str
    warehouse_id: int
    warehouse_name: str
    status: str
    scope: str
    remark: str | None
    sku_count: int
    counted_sku_count: int
    difference_sku_count: int
    created_by: int
    created_by_name: str | None
    submitted_at: datetime | None
    confirmed_at: datetime | None
    confirmed_by: int | None
    confirmed_by_name: str | None
    cancelled_at: datetime | None
    cancelled_by: int | None
    created_at: datetime
    updated_at: datetime
    items: list[StocktakeItemOut]


class StocktakeListItem(BaseModel):
    id: int
    stocktake_no: str
    warehouse_id: int
    warehouse_name: str
    scope: str
    status: str
    sku_count: int
    difference_sku_count: int
    created_by_name: str | None
    created_at: datetime


class StocktakeListOut(BaseModel):
    items: list[StocktakeListItem]
    total: int
    page: int
    page_size: int
