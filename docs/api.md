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

依赖不可用时 HTTP 仍为 200，字段标记 `unavailable`。当前 `milestone` 为 `V3`。

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

Swagger：http://localhost:8011/docs
