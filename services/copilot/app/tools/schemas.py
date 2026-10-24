from __future__ import annotations

from datetime import date, datetime

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


class SearchKnowledgeArgs(ToolArgs):
    query: str = Field(min_length=2, max_length=1000, description="要检索的业务规则或制度问题")
    knowledge_base_ids: list[int] = Field(
        min_length=1,
        max_length=20,
        description="用户明确选择的知识库 ID；不得由模型填写租户或用户身份",
    )
    strategy: str = Field(default="HYBRID", pattern="^(VECTOR|KEYWORD|HYBRID)$")
    top_k: int = Field(default=5, ge=1, le=settings.knowledge_top_k_max)
    rerank: bool = Field(
        default=True, description="请求 Knowledge 使用现有 Rerank；失败时由其明确降级"
    )


class ListKnowledgeBasesArgs(ToolArgs):
    q: str | None = Field(default=None, max_length=100, description="按知识库名称筛选可访问范围")
    page: int = Field(default=1, ge=1, le=20)
    page_size: int = Field(default=20, ge=1, le=20)


class AnalyzeInventoryCoverageArgs(ToolArgs):
    sku_code: str = Field(min_length=1, max_length=64, description="要分析的精确 SKU 编码")
    start_date: date = Field(description="销量统计开始日期，含当天")
    end_date: date = Field(description="销量统计结束日期，含当天")
    warehouse_id: int | None = Field(default=None, gt=0, description="可选仓库；为空时汇总全部仓库")

    @model_validator(mode="after")
    def validate_range(self) -> AnalyzeInventoryCoverageArgs:
        if self.end_date < self.start_date:
            raise ValueError("end_date 不得早于 start_date")
        if (self.end_date - self.start_date).days > 365:
            raise ValueError("统计区间不得超过 366 天")
        return self
