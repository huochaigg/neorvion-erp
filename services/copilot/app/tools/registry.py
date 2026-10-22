from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.ai.types import ModelToolDefinition
from app.core.permissions import PermissionCode
from app.erp.client import ErpApiClient
from app.tools.schemas import (
    GetAfterSaleArgs,
    GetInventoryArgs,
    GetProductArgs,
    GetSalesOrderArgs,
    GetWarehouseArgs,
    ListPurchaseOrdersArgs,
    ListSalesOrdersArgs,
    SearchProductsArgs,
)

_SAFE_FIELDS = frozenset(
    {
        "id",
        "items",
        "total",
        "page",
        "page_size",
        "order_no",
        "external_order_no",
        "warehouse_id",
        "warehouse_name",
        "status",
        "source",
        "currency_code",
        "sku_count",
        "total_quantity",
        "total_amount",
        "created_at",
        "updated_at",
        "submitted_at",
        "confirmed_at",
        "cancelled_at",
        "cancel_reason",
        "sku_id",
        "sku_code",
        "sku_name",
        "product_id",
        "product_name",
        "spec_values",
        "quantity",
        "unit_price",
        "line_amount",
        "reserved_quantity",
        "outbound_quantity",
        "shipped_quantity",
        "current_quantity",
        "current_reserved_quantity",
        "current_available_quantity",
        "remark",
        "name",
        "code",
        "category_id",
        "category_name",
        "brand_id",
        "brand_name",
        "description",
        "skus",
        "barcode",
        "available_quantity",
        "supplier_id",
        "supplier_name",
        "expected_arrival_date",
        "received_quantity",
        "returned_quantity",
        "returnable_quantity",
        "type",
        "is_default",
        "after_sale_no",
        "sales_order_id",
        "sales_order_no",
        "reason",
        "requested_refund_amount",
        "approved_refund_amount",
        "refund_status",
        "return_quantity",
        "approved_at",
        "rejected_at",
        "reject_reason",
        "completed_at",
        "original_quantity",
        "approved_return_quantity",
    }
)


def _safe_projection(value: Any) -> Any:
    if isinstance(value, list):
        return [_safe_projection(item) for item in value]
    if isinstance(value, dict):
        return {key: _safe_projection(item) for key, item in value.items() if key in _SAFE_FIELDS}
    return value


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    permission: str
    path: str
    detail_arg: str | None = None

    def definition(self) -> ModelToolDefinition:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    async def execute(
        self,
        client: ErpApiClient,
        args: BaseModel,
        *,
        access_token: str,
        tenant_id: int,
        request_id: str,
    ) -> Any:
        values = args.model_dump(mode="json", exclude_none=True)
        path = self.path
        if self.detail_arg:
            identifier = values.pop(self.detail_arg, None)
            if identifier is not None:
                path = f"{path}/{identifier}"
        data = await client.get(
            path,
            params=values or None,
            access_token=access_token,
            tenant_id=tenant_id,
            request_id=request_id,
        )
        return _safe_projection(data)


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs = {spec.name: spec for spec in specs}

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def definitions(self, permissions: frozenset[str]) -> list[ModelToolDefinition]:
        return [
            spec.definition() for spec in self._specs.values() if spec.permission in permissions
        ]


def build_tool_registry() -> ToolRegistry:
    """注册经过审查的 GET 工具；刻意不注册低库存阈值和任何写操作。"""
    return ToolRegistry(
        [
            ToolSpec(
                "get_sales_order",
                "按主键查询销售订单详情。",
                GetSalesOrderArgs,
                PermissionCode.ORDER_READ.value,
                "/api/v1/sales-orders",
                "order_id",
            ),
            ToolSpec(
                "list_sales_orders",
                "按订单号、SKU、商品、状态或时间查询销售订单。",
                ListSalesOrdersArgs,
                PermissionCode.ORDER_READ.value,
                "/api/v1/sales-orders",
            ),
            ToolSpec(
                "get_inventory",
                "查询指定 SKU 或库存记录的客观在库、预占和可用数量；不判断补货。",
                GetInventoryArgs,
                PermissionCode.INVENTORY_READ.value,
                "/api/v1/inventory",
                "inventory_id",
            ),
            ToolSpec(
                "get_product",
                "按主键查询商品和 SKU。",
                GetProductArgs,
                PermissionCode.PRODUCT_READ.value,
                "/api/v1/products",
                "product_id",
            ),
            ToolSpec(
                "search_products",
                "按商品关键词或 SKU 编码搜索商品。",
                SearchProductsArgs,
                PermissionCode.PRODUCT_READ.value,
                "/api/v1/products",
            ),
            ToolSpec(
                "list_purchase_orders",
                "查询采购订单列表。",
                ListPurchaseOrdersArgs,
                PermissionCode.PURCHASE_READ.value,
                "/api/v1/purchase-orders",
            ),
            ToolSpec(
                "get_warehouse",
                "按主键查询仓库；联系方式与详细地址不会提供给模型。",
                GetWarehouseArgs,
                PermissionCode.WAREHOUSE_READ.value,
                "/api/v1/warehouses",
                "warehouse_id",
            ),
            ToolSpec(
                "get_after_sale",
                "按主键查询售后单。",
                GetAfterSaleArgs,
                PermissionCode.AFTER_SALE_READ.value,
                "/api/v1/after-sales",
                "after_sale_id",
            ),
        ]
    )
