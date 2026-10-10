# 数据库说明

使用 **共享 MySQL + 共享业务表 + tenant_id**，不用每租户独立库。

当前里程碑 V2.3.1 已创建：

- `users`：全局用户身份，**没有** `tenant_id`
- `tenants`：企业；`code` 唯一，不用名称当唯一键
- `tenant_members`：用户与企业的多对多；`UNIQUE(tenant_id, user_id)`；另有 `UNIQUE(tenant_id, id)` 供 RBAC 复合外键
- `permissions`：平台权限目录；`UNIQUE(code)`
- `roles`：租户角色；`UNIQUE(tenant_id, code)`
- `member_roles`：成员与角色；复合外键保证同一租户
- `role_permissions`：角色与权限

当前里程碑 V2.3.4 增加：

- `users.must_change_password`：管理员代建账号后必须改密

当前里程碑 V2.3.5 增加：

- `tenant_members.display_name`：企业内展示名，可空
- 细粒度权限 seed 与旧 `*:manage` 展开（不删旧 code）

当前里程碑 V3 增加：

- `product_categories`：租户类目树；`UNIQUE(tenant_id, id)`；`parent_id` 与 `tenant_id` 复合外键指向本表
- `brands`：租户品牌；`UNIQUE(tenant_id, code)`
- `products`：SPU；`UNIQUE(tenant_id, code)`；类目/品牌复合外键保证同租户
- `product_skus`：SKU；`UNIQUE(tenant_id, sku_code)`；`spec_values` JSON；商品复合外键保证同租户

当前里程碑 V4 增加：

- `warehouses`：租户仓库档案；`UNIQUE(tenant_id, code)`；创建时可空编码，flush 后写入 `WH` + 10 位 id
- 联合索引 `(tenant_id, status)`、`(tenant_id, type)`
- 默认仓由 Service 事务 + `SELECT ... FOR UPDATE` 保证每租户最多一个，不在 MySQL 上做部分唯一约束

当前里程碑 V5 增加：

- `inventories`：`UNIQUE(tenant_id, warehouse_id, sku_id)`；CHECK 数量非负且预占不超过实际；可用库存不落库
- `inventory_transactions`：只追加的库存流水
- 复合外键保证仓库 / SKU 与库存同租户

当前里程碑 V6 增加：

- `suppliers`：租户供应商；`UNIQUE(tenant_id, code)`；未填编码时 flush 后写 `SUP` + 10 位 id
- `purchase_orders`：采购单；`UNIQUE(tenant_id, order_no)`；供应商 / 仓库复合外键
- `purchase_order_items`：采购明细；`UNIQUE(tenant_id, purchase_order_id, sku_id)`；`received_quantity` 预留给收货版本
- 状态流转用条件 UPDATE；草稿编辑用 `SELECT ... FOR UPDATE`

当前里程碑 V7 增加：

- `customers`：租户客户；`UNIQUE(tenant_id, code)`；未填编码时 flush 后写 `CUS` + 10 位 id
- `sales_orders`：销售订单；`UNIQUE(tenant_id, order_no)`；`UNIQUE(tenant_id, source, external_order_no)` 允许多个空平台单号；收货地址是下单快照
- `sales_order_items`：销售明细；`UNIQUE(tenant_id, sales_order_id, sku_id)`；V9 起 `reserved + outbound <= quantity` 且 `shipped <= outbound`

当前里程碑 V8 增加：

- `purchase_receipts` / `purchase_receipt_items`：收货单。单号 `PR` + 年 + 6 位 id。确认后才增加库存
- `outbound_orders` / `outbound_order_items`：出库单。单号 `OUT` + 年 + 6 位 id。拣货不改库存，确认出库才扣减
- 迁移 `20261006_0013` 只改 CHECK，不重建销售明细表
- `outbound_picks` / `outbound_pick_lines`：每次拣货追加记录。`quantity` 是本次，`picked_before` / `picked_after` 是累计变化。出库明细 `picked_quantity` 仍是累计，确认出库继续用它

当前里程碑 V10 增加：

- `stocktake_orders` / `stocktake_items`：盘点单。单号 `ST` + 年 + 6 位 id。明细保存账面快照，确认时按差异调整库存
- `stock_transfers` / `stock_transfer_items`：调拨单。单号 `TR` + 年 + 6 位 id。调出仓不能等于调入仓
- `inventory_transactions.type` 加长到 32，以容纳 `STOCKTAKE_ADJUSTMENT`

当前里程碑 V9 增加：

- `carriers`：物流商；`UNIQUE(tenant_id, code)`；未填编码时 flush 后写 `CAR` + 10 位 id
- `shipments`：物流单；`UNIQUE(tenant_id, shipment_no)`；`UNIQUE(tenant_id, carrier_id, tracking_no)`
- `shipment_items`：本包裹实际发给承运商的数量；同一出库明细可拆多包裹
- `shipment_tracking_events`：只追加的手工轨迹
- 迁移 `20261008_0015` 把 V8 的 `shipped_quantity` 拷到 `outbound_quantity` 后清零，并把 `PARTIALLY_SHIPPED` / `SHIPPED` 改成 `PARTIALLY_OUTBOUND` / `OUTBOUNDED`

所有业务表必须包含 `tenant_id`（`TenantMixin`），唯一约束必须带上租户，例如：

```sql
UNIQUE (tenant_id, sku_code)
UNIQUE (tenant_id, warehouse_id, sku_id)
```

正式建表只通过 Alembic，不在运行时 `create_all`。

连接配置见 `.env.example`。SQLAlchemy 2.x 使用同步 `Session`。库存调整使用 `SELECT ... FOR UPDATE`；预占用条件 UPDATE。
