from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InventoryInitialize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: int = Field(gt=0)
    sku_id: int = Field(gt=0)
    quantity: int = Field(ge=0)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class InventoryAdjust(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=16)
    quantity: int = Field(ge=1)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def allow_adjust_types(self) -> InventoryAdjust:
        if self.type not in {"ADJUST_IN", "ADJUST_OUT"}:
            raise ValueError("调整类型只能是 ADJUST_IN 或 ADJUST_OUT")
        return self


class InventoryQtyChange(BaseModel):
    """内部预占 / 释放 / 扣减请求。不出现在 ERP 菜单。"""

    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class InventoryOptimisticAdjust(BaseModel):
    """乐观锁演示：按 expected_version 条件更新实际库存。"""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    type: str = Field(min_length=1, max_length=16)
    quantity: int = Field(ge=1)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def allow_adjust_types(self) -> InventoryOptimisticAdjust:
        if self.type not in {"ADJUST_IN", "ADJUST_OUT"}:
            raise ValueError("调整类型只能是 ADJUST_IN 或 ADJUST_OUT")
        return self


class InventoryItemOut(BaseModel):
    id: int
    tenant_id: int
    warehouse_id: int
    warehouse_name: str
    sku_id: int
    sku_code: str
    sku_name: str
    product_id: int
    product_name: str
    spec_values: dict[str, Any]
    quantity: int
    reserved_quantity: int
    available_quantity: int
    version: int
    created_at: datetime
    updated_at: datetime


class InventoryListOut(BaseModel):
    items: list[InventoryItemOut]
    total: int
    page: int
    page_size: int


class InventoryTransactionOut(BaseModel):
    id: int
    tenant_id: int
    inventory_id: int
    warehouse_id: int
    warehouse_name: str
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    type: str
    change_quantity: int
    before_quantity: int
    after_quantity: int
    before_reserved_quantity: int
    after_reserved_quantity: int
    reference_type: str | None
    reference_id: int | None
    remark: str | None
    operator_user_id: int | None
    operator_name: str | None
    created_at: datetime


class InventoryTransactionListOut(BaseModel):
    items: list[InventoryTransactionOut]
    total: int
    page: int
    page_size: int


class InventoryDetailOut(InventoryItemOut):
    recent_transactions: list[InventoryTransactionOut] = Field(default_factory=list)


class SkuOptionOut(BaseModel):
    id: int
    tenant_id: int
    product_id: int
    product_name: str
    sku_code: str
    name: str
    spec_values: dict[str, Any]
    status: str


class SkuOptionListOut(BaseModel):
    items: list[SkuOptionOut]
    total: int
    page: int
    page_size: int


class SkuAvailabilityOut(BaseModel):
    warehouse_id: int
    sku_id: int
    quantity: int
    reserved_quantity: int
    available_quantity: int
    initialized: bool


class SkuAvailabilityListOut(BaseModel):
    items: list[SkuAvailabilityOut]
