# 库存管理

当前里程碑 **V5**。库存不是 `SKU → quantity`，而是：

```text
Tenant + Warehouse + SKU → Inventory
```

同一 SKU 在深圳仓、广州仓、美国仓可以有完全不同的数量。唯一约束是 `UNIQUE(tenant_id, warehouse_id, sku_id)`。

本版完成：库存台账、初始化、调整、流水、预占/释放/出库扣减底层能力、并发安全、RBAC、React 页面。采购单见 V6 `docs/purchases.md`。

**不**开发：采购单、销售订单、正式采购入库/销售出库页面、物流、发货、平台订单。那些是后续版本。`INBOUND` / `OUTBOUND` 枚举已预留；`reserve` / `release` / `deduct-reserved` 只作为内部 Service（测试 API 有，ERP 菜单没有「手动预占」按钮）。

## 三个数量

| 字段 | 存库？ | 含义 |
| --- | --- | --- |
| `quantity` | 是 | 实际账面库存，货还在仓里的数字 |
| `reserved_quantity` | 是 | 已被业务预占、尚未正式出库 |
| `available_quantity` | **否** | `quantity - reserved_quantity`，查询时计算 |

不把可用库存存成第三列，避免三个数字互相打架。Service 与列表 SQL 都用减法。

约束（数据库 CHECK + Service 双重校验）：

- `quantity >= 0`
- `reserved_quantity >= 0`
- `reserved_quantity <= quantity`

MySQL 8.0.16+ 会执行 CHECK。即便如此，业务校验仍必须做：数据库是最后一道防线。

## Inventory 与 InventoryTransaction

- **Inventory**：当前状态。一行 = 某租户某仓库某个 SKU 现在有多少。
- **InventoryTransaction**：变化历史。只追加，普通业务不允许改或删。

如果盘点把 100 错加到 120，不要改历史，再做一笔 `ADJUST_OUT -20` 回到 100。

库存数字和流水必须在**同一个事务**里提交：

```text
BEGIN
锁住 / 条件更新库存行
修改 Inventory
INSERT InventoryTransaction
COMMIT
```

任一步失败 `ROLLBACK`。不能先提交库存再插流水，否则流水失败时账面已经变了、历史却不存在。

## 表结构

迁移：`backend/alembic/versions/20261004_0010_create_inventory_tables.py`

### inventories

| 列 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `tenant_id` | 所属企业 |
| `warehouse_id` / `sku_id` | 仓库与 SKU，复合外键保证同租户 |
| `quantity` / `reserved_quantity` | 实际 / 预占 |
| `version` | 乐观锁版本，默认 0，每次关键修改 +1 |
| `created_at` / `updated_at` | 时间戳 |

`UNIQUE(tenant_id, warehouse_id, sku_id)`。复合外键依赖 `warehouses` / `product_skus` 上的 `UNIQUE(tenant_id, id)`。

### inventory_transactions

| 列 | 说明 |
| --- | --- |
| `type` | 见下方枚举 |
| `change_quantity` | 实际库存变化，预占/释放为 0 |
| `before_quantity` / `after_quantity` | 变化前后实际库存 |
| `before_reserved_quantity` / `after_reserved_quantity` | 变化前后预占 |
| `reference_type` / `reference_id` | 关联单据，V5 通常为空 |
| `remark` | 备注 |
| `operator_user_id` | 操作人，用户删除后 SET NULL |
| `created_at` | 流水时间，无 `updated_at` |

## 流水类型

| 值 | 界面 | V5 |
| --- | --- | --- |
| `INITIALIZE` | 初始化 | 使用 |
| `ADJUST_IN` / `ADJUST_OUT` | 库存增加 / 减少 | 使用 |
| `RESERVE` / `RELEASE` | 预占 / 释放 | 底层实现，不进业务菜单 |
| `INBOUND` / `OUTBOUND` | 入库 / 出库 | 枚举预留；扣减预占流水记 `OUTBOUND` |

## 初始化

某仓库 + SKU 还没有 Inventory 时：

- 创建 `quantity = n`（允许 0）、`reserved_quantity = 0`
- 同时写 `INITIALIZE` 流水：`before=0, after=n, change=+n`

已经存在则拒绝：`40950` `INVENTORY_ALREADY_EXISTS`，请走调整。

仓库、SKU 必须属于当前租户。停用仓不能初始化。Tenant A 不能拿 Tenant B 的 `warehouse_id` / `sku_id`。

## 调整

前端提交增量，不要提交「把库存改成 200」：

```json
{ "type": "ADJUST_IN", "quantity": 20, "remark": "盘点补差" }
{ "type": "ADJUST_OUT", "quantity": 5, "remark": "盘点纠正" }
```

`ADJUST_OUT` 必须 `quantity - reduce >= reserved_quantity`，也就是不能把已经预占的货减没。否则 `40070` `INSUFFICIENT_AVAILABLE_INVENTORY`。

例如实际 100、预占 30、可用 70：手工减 80 后会变成实际 20、预占 30，违反 `reserved <= quantity`。

正式调整走 **SELECT FOR UPDATE**，见下。

## 为什么预占不直接减少 quantity

后续订单占用库存时，货还在仓库里等发。如果预占直接减 `quantity`，盘点会以为货已经没了。所以：

- `reserve`：只增加 `reserved_quantity`
- `release`：只减少 `reserved_quantity`，不能减成负数
- `deduct_reserved_inventory`（出库确认）：`quantity` 和 `reserved` **同时**减少。预占 10 再发货 10，应从 `100/10` 变成 `90/0`，而不是 `90/10`

V5 不提供发货页面，只把原语和单测留下给出库版本。

## 三种并发方案

本版**不**在同一条业务路径里混用 FOR UPDATE 和 version，避免逻辑缠在一起。

### 1. SELECT FOR UPDATE（悲观锁）— 正式调整

`InventoryRepository.get_for_update()`：

```python
select(Inventory).where(
    Inventory.tenant_id == tenant_id,
    Inventory.id == inventory_id,
).with_for_update()
```

流程：begin → 锁行 → 读 quantity/reserved → 校验 → 改库存 → 写流水 → commit → 释放锁。两个管理员同时调整同一行时，后到的请求会等到前一个结束，看到的是已经改过的数字。

适合：手工盘点、需要读完再按业务规则分支的写操作。持锁时间要短，只锁必要的行，WHERE 必须带 `tenant_id`。

隔离级别：默认 REPEATABLE READ 下，FOR UPDATE 锁住当前行直到事务结束。两个事务不会同时按过期快照改同一行。

死锁：两个事务交叉锁不同行时可能互等。本版调整只锁一行，预占用无锁条件 UPDATE，交叉死锁面很小。一旦出现 MySQL 会让一方回滚，Service 捕获后返回业务错误，不要把半成品提交。

### 2. 条件 UPDATE + rowcount — 预占 / 释放 / 扣减

```sql
UPDATE inventories
SET reserved_quantity = reserved_quantity + :qty,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND warehouse_id = :warehouse_id
  AND sku_id = :sku_id
  AND quantity - reserved_quantity >= :qty
```

检查 `rowcount`：

- `1`：成功
- `0`：记录不存在或可用不够，再查一次区分错误

为什么能防超卖：数据库在 SET 时用**当前行**判断可用量。不会出现「两个请求都先读到 available=10，再各自扣 8」。

`release` 条件是 `reserved_quantity >= qty`。`deduct` 条件是 reserved 和 quantity 都够。

Core `UPDATE` 不会刷新 SQLAlchemy identity map，Repository 在 execute 后 `expire_all()`，随后读取才是新数字。

### 3. version 乐观锁 — 仅演示

```sql
UPDATE inventories
SET quantity = :new_quantity, version = version + 1
WHERE id = :id AND tenant_id = :tenant_id AND version = :old_version
```

`rowcount == 0` → `40072` `INVENTORY_CONFLICT`，调用方应重新读取。接口：`POST /inventory/{id}/optimistic-adjust`，**不进 ERP 菜单**。正式盘点请用悲观锁调整。

`version` 在条件 UPDATE / FOR UPDATE 成功后也会 +1，方便以后扩展，但那两条路径不以 version 当互斥条件。

## 多租户

Inventory、流水都有 `tenant_id`。查询、锁、条件 UPDATE 都必须带当前 `TenantContext.tenant_id`。仓库和 SKU 用复合外键绑在同一租户。列表 JOIN 仓库/SKU/SPU，避免循环里再查名称（N+1）。

不要用 Redis 缓存 `quantity`。库存是强一致、高频变化的数据，缓存和数据库很容易不一致。报表只读场景以后再说。

## 权限

| 编码 | 用途 |
| --- | --- |
| `inventory:read` | 列表 / 详情 / 菜单 |
| `inventory:initialize` | 初始化 |
| `inventory:adjust` | 调整；内部预占/释放/扣减也校验它 |
| `inventory:transaction:read` | 流水 |
| `inventory:inbound` / `inventory:outbound` | 预留，不删 |

默认模板：OWNER / ADMIN 全部；OPERATOR 与 VIEWER 只读台账和流水；WAREHOUSE 可读、初始化、调整、看流水。最终仍看 `role_permissions`，不按角色名判断。

已被库存引用的仓库 / SKU **不能物理删除**，只允许停用。

## API

需要登录和 `X-Tenant-ID`。

- `GET /api/v1/inventory` 分页：`q` / `sku_code` / `warehouse_id` / `category_id` / `brand_id` / `stock_status`（`IN_STOCK` / `ZERO` / `LOW`）/ `threshold`（低库存阈值，默认 10，不写进表）
- `GET /api/v1/inventory/{id}`
- `POST /api/v1/inventory/initialize`
- `POST /api/v1/inventory/{id}/adjust`
- `GET /api/v1/inventory/transactions`
- `GET /api/v1/inventory/{id}/transactions`
- `GET /api/v1/product-skus`（`product:read`，初始化下拉远程搜索）
- 内部：`POST .../reserve`、`/release`、`/deduct-reserved`、`/optimistic-adjust`

错误：已存在 `40950`；可用不足 `40070`；预占不足 `40071`；乐观冲突 `40072`；跨租户库存 `40450`、仓库 `40440`、SKU `40433`。

## 前端

- `/inventory/list` 列表：筛选、初始化 Drawer、调整 Drawer
- `/inventory/transactions` 流水
- `/inventory/:id` 详情（菜单隐藏）

Query Key：`['tenant', tenantId, 'inventory', params]`。调整成功后 invalidate 列表、详情、流水。切租户走现有隔离。SKU 下拉远程搜索，不要一次拉全表。
