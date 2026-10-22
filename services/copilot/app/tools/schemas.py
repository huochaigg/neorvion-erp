from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetSalesOrderArgs(ToolArgs):
    order_id: int = Field(gt=0, description="销售订单主键，不是租户或外部订单号")


class ListSalesOrdersArgs(ToolArgs):
    q: str | None = Field(default=None, max_length=64, description="订单号或客户名称关键词")
    order_no: str | None = Field(default=None, max_length=64)
    sku_code: str | None = Field(default=None, max_length=64)
    product_name: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=24, description="ERP 精确订单状态")
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: int = Field(default=1, ge=1, le=20)
    page_size: int = Field(default=20, ge=1, le=settings.tool_max_page_size)


class GetInventoryArgs(ToolArgs):
    inventory_id: int | None = Field(default=None, gt=0)
    sku_code: str | None = Field(default=None, max_length=64)
    q: str | None = Field(default=None, max_length=64, description="SKU 或商品名称关键词")
    warehouse_id: int | None = Field(default=None, gt=0)
    page: int = Field(default=1, ge=1, le=20)
    page_size: int = Field(default=20, ge=1, le=settings.tool_max_page_size)

    @model_validator(mode="after")
    def require_lookup(self) -> GetInventoryArgs:
        if self.inventory_id is None and not self.sku_code and not self.q:
            raise ValueError("inventory_id、sku_code、q 至少提供一个")
        return self


class GetProductArgs(ToolArgs):
    product_id: int = Field(gt=0)


class SearchProductsArgs(ToolArgs):
    q: str | None = Field(default=None, max_length=64, description="商品名称或编码关键词")
    sku_code: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=16)
    page: int = Field(default=1, ge=1, le=20)
    page_size: int = Field(default=20, ge=1, le=settings.tool_max_page_size)

    @model_validator(mode="after")
    def require_lookup(self) -> SearchProductsArgs:
        if not self.q and not self.sku_code:
            raise ValueError("q、sku_code 至少提供一个")
        return self


class ListPurchaseOrdersArgs(ToolArgs):
    q: str | None = Field(default=None, max_length=64)
    supplier_id: int | None = Field(default=None, gt=0)
    warehouse_id: int | None = Field(default=None, gt=0)
    sku_id: int | None = Field(default=None, gt=0)
    status: str | None = Field(default=None, max_length=24)
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: int = Field(default=1, ge=1, le=20)
    page_size: int = Field(default=20, ge=1, le=settings.tool_max_page_size)


class GetWarehouseArgs(ToolArgs):
    warehouse_id: int = Field(gt=0)


class GetAfterSaleArgs(ToolArgs):
    after_sale_id: int = Field(gt=0)
