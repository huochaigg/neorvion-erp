# 商品管理（SPU / SKU / 类目 / 品牌）

V3 完成商品档案闭环。库存、采购、销售订单、出入库、物流不在本版。

## SPU 和 SKU

**SPU**（`products`）是一类商品的公共档案。例如「Apple iPhone 17」：名称、内部编码、类目、品牌、描述、状态。

**SKU**（`product_skus`）是真正可销售、后续可管库存的最小单位。例如：

- iPhone 17 / 黑色 / 256GB
- iPhone 17 / 白色 / 512GB

一个 SPU 可以有多个 SKU。库存、采购、订单以后必须关联 SKU，不能直接给 SPU 建库存数量。

商品内部编码 `code` 和 SKU 编码 `sku_code` 都是租户内唯一的业务编号，不要用数据库自增 id 当货号。

状态：

- SPU：`DRAFT` / `ACTIVE` / `INACTIVE`
- SKU：`ACTIVE` / `INACTIVE`

## 类目

`product_categories` 按 `parent_id` 自关联，最多三级：

```text
电子产品
  手机
    智能手机
```

类目属于租户。A 企业的类目不能被 B 企业的商品引用。同一父节点下名称不能重复。

删除规则（服务端最终校验，前端提示不能代替）：

- 有子类目 → `CATEGORY_HAS_CHILDREN`（40050）
- 已有商品使用 → `CATEGORY_IN_USE`（40051）
- 不级联删除商品

## 品牌

`brands` 也是租户私有。`code` 在同一企业内唯一，不同企业可以都叫 `NIKE`。

已被商品使用 → `BRAND_IN_USE`（40052）。Logo 本版只填 URL，不单独做 OSS。

## spec_values

V3 不引入 EAV 或规格笛卡尔积。SKU 用 MySQL JSON 保存键值：

```json
{ "color": "黑色", "storage": "256GB" }
```

前端用「规格名 / 规格值」动态行编辑，提交时转成该对象。列表和详情直接展示。

## 商品创建事务

创建商品时，SPU 和本次全部 SKU 必须在同一事务完成：

1. 校验类目、品牌属于当前租户
2. 校验 `code`、全部 `sku_code`（含本次请求内部重复）
3. 写入 `products` 后 `flush` 拿到 `product.id`
4. 写入全部 `product_skus`
5. `commit`

`flush` 不是提交。如果现在就 `commit`，后面某个 SKU 失败只能补偿删除，容易留下「商品在、SKU 缺一半」。任意一步失败 `rollback`。

编辑 SPU 走 `PATCH /products/{id}`。SKU 作为子资源：

- `POST /products/{id}/skus`
- `PATCH /products/{id}/skus/{sku_id}`
- `DELETE /products/{id}/skus/{sku_id}`

V3 还没有库存和订单引用，允许物理删除未被使用的 SKU，但不能删光（至少保留一个）。**一旦 SKU 产生库存或订单，应禁止物理删除、只允许停用。** 不要提前建库存表。

## 多租户隔离

四张表都有 `tenant_id`。列表、详情、更新、删除都必须带当前 `TenantContext`，不能只按全局 id 查询。

`products.category_id` / `products.brand_id` / `product_skus.product_id` 使用复合外键 `(tenant_id, id)`，避免把 A 企业的类目或品牌挂到 B 企业的商品上。

## 数据库关系

```text
Tenant
  ├── ProductCategory（parent_id 自关联，最多三级）
  ├── Brand
  └── Product（SPU）
        └── ProductSku
```

Product 必须属于当前租户的类目；品牌可选，有值时也必须同租户。

## 权限

不新增 `product:sku:manage` 或类目/品牌专用编码。类目和品牌归入现有商品权限：

| 操作 | 权限 |
| --- | --- |
| 查看商品 / 类目 / 品牌 | `product:read` |
| 创建商品 | `product:create` |
| 编辑商品、SKU、类目、品牌 | `product:update` |
| 删除类目、品牌 | `product:delete` |

默认模板：OWNER / ADMIN 全部；OPERATOR 读/建/改（不能删）；WAREHOUSE / VIEWER 只读。最终仍以 `role_permissions` 为准，不按角色名硬编码。

## 本版不包含

仓库、库存数量、库存流水、采购单、销售订单、收货、入库、出库、发货、物流、平台订单同步、AI Agent。
