# API 说明

统一响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

`code = 0` 表示成功。业务错误走 `AppError`。

## 健康检查

`GET /api/v1/health`

依赖不可用时 HTTP 仍为 200，字段标记 `unavailable`。当前 `milestone` 为 `V10`。

## 认证

详见 `docs/auth.md`。

- `GET /api/crypto/public-key`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/change-password`

## 租户

详见 `docs/multi-tenancy.md`。除「创建 / 我的列表」外，租户业务接口使用请求头 `X-Tenant-ID`。

- `POST /api/v1/tenants`
- `GET /api/v1/tenants`
- `GET /api/v1/tenants/current`（需要 `X-Tenant-ID`，含 `permission_codes`）
- `GET /api/v1/tenants/current/my-permissions`（当前成员 `roles` + `permissions`）
- `GET /api/v1/tenants/{tenant_id}`
- `GET /api/v1/tenants/{tenant_id}/members`（分页：`q` / `status` / `page` / `page_size`）
- `POST /api/v1/tenants/{tenant_id}/members`（`email` + `role_ids`，已有账号）
- `POST /api/v1/tenants/{tenant_id}/members/accounts`（代建账号，响应含一次性 `temporary_password`）
- `GET /api/v1/tenants/{tenant_id}/members/{member_id}`
- `GET /api/v1/tenants/{tenant_id}/members/{member_id}/permissions`
- `PUT /api/v1/tenants/{tenant_id}/members/{member_id}/roles`
- `PATCH /api/v1/tenants/{tenant_id}/members/{member_id}`（企业内名称和/或启用禁用）
- `DELETE /api/v1/tenants/{tenant_id}/members/{member_id}`（移出企业，不删 User）

`GET /api/v1/tenants/current` 含 `permission_codes`。`GET /api/v1/tenants/current/my-permissions` 是前端菜单的数据源。

## 角色与权限（V2.3.1）

详见 `docs/rbac.md`。需要登录和 `X-Tenant-ID`。

- `GET /api/v1/permissions`
- `GET /api/v1/permissions/tree`
- `GET /api/v1/roles`
- `POST /api/v1/roles`
- `GET /api/v1/roles/{role_id}`
- `PATCH /api/v1/roles/{role_id}`
- `PUT /api/v1/roles/{role_id}/permissions`
- `DELETE /api/v1/roles/{role_id}`

## 商品（V3）

详见 `docs/products.md`。需要登录和有效 `X-Tenant-ID`。类目/品牌使用商品权限，不另拆编码。

- `GET /api/v1/product-categories`（`product:read`）树
- `POST /api/v1/product-categories`（`product:update`）
- `PATCH /api/v1/product-categories/{id}`（`product:update`）
- `DELETE /api/v1/product-categories/{id}`（`product:delete`）
- `GET /api/v1/brands`（`product:read`）分页
- `GET /api/v1/brands/options`（`product:read`）
- `POST /api/v1/brands`（`product:update`）
- `PATCH /api/v1/brands/{id}`（`product:update`）
- `DELETE /api/v1/brands/{id}`（`product:delete`）
- `GET /api/v1/products`（`product:read`）分页：`q` / `sku_code` / `category_id` / `brand_id` / `status`
- `POST /api/v1/products`（`product:create`）同一事务写入 SPU + SKU
- `GET /api/v1/products/{id}`（`product:read`）
- `PATCH /api/v1/products/{id}`（`product:update`）只改 SPU
- `POST /api/v1/products/{id}/skus`（`product:update`）
- `PATCH /api/v1/products/{id}/skus/{sku_id}`（`product:update`）
- `DELETE /api/v1/products/{id}/skus/{sku_id}`（`product:update`）

有子类目 → `40050` `CATEGORY_HAS_CHILDREN`。类目被商品使用 → `40051` `CATEGORY_IN_USE`。品牌被使用 → `40052` `BRAND_IN_USE`。商品/SKU 编码冲突 → `40930` / `40931`。跨租户资源 → `404`。

## 仓库（V4）

详见 `docs/warehouses.md`。需要登录和有效 `X-Tenant-ID`。

- `GET /api/v1/warehouses`（`warehouse:read`）分页：`q` / `type` / `status`
- `GET /api/v1/warehouses/{id}`（`warehouse:read`）
- `POST /api/v1/warehouses`（`warehouse:create`）
- `PATCH /api/v1/warehouses/{id}`（`warehouse:update`）不改 code / 默认 / 状态
- `PATCH /api/v1/warehouses/{id}/status`（`warehouse:disable`）
- `POST /api/v1/warehouses/{id}/set-default`（`warehouse:update`）
- `DELETE /api/v1/warehouses/{id}`（`warehouse:delete`）

仓库编码冲突 → `40940`。默认仓不能停用 → `40063` `DEFAULT_WAREHOUSE_CANNOT_DISABLE`。默认仓不是最后一个时不能删除 → `40064` `DEFAULT_WAREHOUSE_CANNOT_DELETE`。停用仓不能设默认 → `40065`。已被库存引用 → `40066` `WAREHOUSE_IN_USE`。跨租户 → `40440`。

## 库存（V5）

详见 `docs/inventory.md`。需要登录和有效 `X-Tenant-ID`。

- `GET /api/v1/inventory`（`inventory:read`）分页：`q` / `sku_code` / `warehouse_id` / `category_id` / `brand_id` / `stock_status` / `threshold`
- `GET /api/v1/inventory/{id}`（`inventory:read`）
- `POST /api/v1/inventory/initialize`（`inventory:initialize`）
- `POST /api/v1/inventory/{id}/adjust`（`inventory:adjust`）
- `GET /api/v1/inventory/transactions`（`inventory:transaction:read`）
- `GET /api/v1/inventory/{id}/transactions`（`inventory:transaction:read`）
- `GET /api/v1/product-skus`（`product:read`）初始化下拉远程搜索
- 内部：`POST /inventory/{id}/reserve|release|deduct-reserved|optimistic-adjust`（`inventory:adjust`，不进业务菜单）

已存在 → `40950` `INVENTORY_ALREADY_EXISTS`。可用不足 → `40070`。预占不足 → `40071`。乐观锁冲突 → `40072`。跨租户库存 → `40450`。

## 采购（V6）

详见 `docs/purchases.md`。需要登录和有效 `X-Tenant-ID`。审核通过不改库存。

- `GET /api/v1/suppliers`（`supplier:read`）分页：`q` / `status` / `country_code`
- `POST /api/v1/suppliers`（`supplier:create`）
- `GET /api/v1/suppliers/{id}`（`supplier:read`）
- `PATCH /api/v1/suppliers/{id}`（`supplier:update`）
- `PATCH /api/v1/suppliers/{id}/status`（`supplier:disable`）
- `DELETE /api/v1/suppliers/{id}`（`supplier:delete`）
- `GET /api/v1/purchase-orders`（`purchase:read`）分页：`q` / `supplier_id` / `warehouse_id` / `sku_id` / `status` / 日期
- `POST /api/v1/purchase-orders`（`purchase:create`）同一事务写入主表 + 明细
- `GET /api/v1/purchase-orders/{id}`（`purchase:read`）
- `PATCH /api/v1/purchase-orders/{id}`（`purchase:update`）仅 DRAFT / REJECTED
- `POST /api/v1/purchase-orders/{id}/submit|approve|reject|cancel`

供应商编码冲突 → `40960`。使用中不能删除 → `40081` `SUPPLIER_IN_USE`。非法状态流转 → `40090`。不可编辑 → `40091`。并发审核冲突 → `40095` `PURCHASE_ORDER_STATE_CONFLICT`。跨租户采购单 → `40470`。

## 销售订单（V7）

详见 `docs/orders.md`。需要登录和有效 `X-Tenant-ID`。确认只预占库存，不减少实际数量。

- `GET /api/v1/customers`（`customer:read`）分页：`q` / `status`
- `POST /api/v1/customers`（`customer:create`）
- `GET /api/v1/customers/{id}`（`customer:read`）
- `PATCH /api/v1/customers/{id}`（`customer:update`）
- `PATCH /api/v1/customers/{id}/status`（`customer:disable`）
- `DELETE /api/v1/customers/{id}`（`customer:delete`）
- `GET /api/v1/sales-orders`（`order:read`）分页：订单号、平台单号、客户、仓库、SKU、商品名、状态、来源、创建日期
- `POST /api/v1/sales-orders`（`order:create`）同一事务写入主表 + 明细
- `GET /api/v1/sales-orders/{id}`（`order:read`）
- `PATCH /api/v1/sales-orders/{id}`（`order:update`）仅 DRAFT
- `POST /api/v1/sales-orders/{id}/submit|confirm|cancel`
- `GET /api/v1/inventory/availability`（`inventory:read`）按仓库和 SKU 返回可用量，只作提示

客户编码冲突 → `40961`。使用中不能删除 → `40085` `CUSTOMER_IN_USE`。停用客户建单 → `40119`。重复 SKU → `40111`。不可编辑 → `40112`。非法流转 → `40114`。状态冲突 → `40115`。已取消 → `40117` `ORDER_ALREADY_CANCELLED`。已出库不能整单取消 → `40120` `SALES_ORDER_HAS_SHIPMENTS`。库存不足 → `40070`，`data.items` 列出 SKU、需求量和可用量。平台单号冲突 → `40962`。跨租户订单 → `40471`。

## 采购收货与销售出库（V8）

详见 `docs/fulfillment.md`。

- `GET/POST /api/v1/purchase-receipts`
- `GET/PATCH /api/v1/purchase-receipts/{id}`
- `POST /api/v1/purchase-receipts/{id}/confirm|cancel`
- `GET/POST /api/v1/outbound-orders`
- `GET /api/v1/outbound-orders/{id}`
- `POST /api/v1/outbound-orders/{id}/pick|confirm|cancel`

重复确认收货 → `40131` `PURCHASE_RECEIPT_ALREADY_CONFIRMED`。超额收货 → `40132`。重复确认出库 → `40141` `OUTBOUND_ALREADY_CONFIRMED`。出库超过预占 → `40142`。跨租户单据 → `40480` / `40481`。

## 物流商与物流单（V9）

详见 `docs/shipping.md`。

- `GET/POST /api/v1/carriers`
- `GET/PATCH /api/v1/carriers/{id}`
- `PATCH /api/v1/carriers/{id}/status`
- `DELETE /api/v1/carriers/{id}`
- `GET/POST /api/v1/shipments`
- `GET/PATCH /api/v1/shipments/{id}`
- `POST /api/v1/shipments/{id}/confirm|cancel|deliver`
- `GET/POST /api/v1/shipments/{id}/tracking-events`

物流商编码冲突 → `40970`。使用中不能删除 → `40096` `CARRIER_IN_USE`。停用承运商发货 → `CARRIER_DISABLED`。运单号冲突 → `40971`。重复确认发货 → `40151` `SHIPMENT_ALREADY_CONFIRMED`。超过出库剩余 → `40152` `SHIPMENT_EXCEEDS_OUTBOUND`。确认前无运单号 → `40153` `SHIPMENT_TRACKING_REQUIRED`。跨租户 → `40490` / `40491`。确认发货不修改库存。

## 盘点与调拨（V10）

详见 `docs/stocktake.md`、`docs/stock-transfer.md`。

- `GET/POST /api/v1/stocktakes`
- `GET/PATCH /api/v1/stocktakes/{id}`
- `PUT /api/v1/stocktakes/{id}/items`
- `POST /api/v1/stocktakes/{id}/submit|confirm|cancel`
- `GET/POST /api/v1/stock-transfers`
- `GET/PATCH /api/v1/stock-transfers/{id}`
- `POST /api/v1/stock-transfers/{id}/submit|confirm-outbound|confirm-receive|cancel`

重复确认盘点 → `40203` `STOCKTAKE_ALREADY_CONFIRMED`。盘亏低于预占 → `40204` `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`。重复调出 → `40224`。重复调入 → `40225`。在途不能取消 → `40226`。跨租户 → `40492` / `40493`。

Swagger：http://localhost:8011/docs
