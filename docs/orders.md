# 销售订单

当前里程碑 **V7 起的销售订单**。拣货和正式出库见 `docs/fulfillment.md`。销售订单表示企业向客户销售一批 SKU，并在确认后预占履约仓库的可用库存。

```text
创建客户 → 创建销售订单草稿 → 提交待确认 → 确认并预占 → 待出库
                                                      ↘ 取消并释放预占
```

预占只增加 `Inventory.reserved_quantity`，**不**减少 `Inventory.quantity`。可用量 = 实际 − 预占，所以确认后可用量下降，货仍在仓库里。

正式出库在 V8：确认出库时同时减少 `quantity` 和 `reserved_quantity`。物流发货、签收、订单完成在 V9，见 `docs/shipping.md`。平台订单同步、退货退款仍未做。

## 为什么草稿不预占

用户可能先建单，再去补货。创建和保存草稿只写订单自己的表。库存不足可以提示，不能阻止保存。真正的库存校验发生在确认。

提交（`DRAFT` → `PENDING_CONFIRMATION`）同样不预占。提交只表示业务上可以交给审核人，仓库还没有被这张单占住。

## 为什么确认才预占，而且不减实际库存

确认（`POST /sales-orders/{id}/confirm`，权限 `order:audit`）表示这张单已经成立，对应数量不能再卖给别人。

货还没有离开仓库，所以：

- `quantity` 不变
- `reserved_quantity` 增加购买数量
- 明细 `SalesOrderItem.reserved_quantity = quantity`
- 流水类型 `RESERVE`，`reference_type = SALES_ORDER`，`reference_id = 订单 id`，备注里写订单号

正式出库在 V8：同时减少 `quantity` 和 `reserved_quantity`，并增加明细 `outbound_quantity`、减少仍占用的 `reserved_quantity`。V9 的 `shipped_quantity` 表示已经交给承运商的数量。约束是 `reserved_quantity + outbound_quantity <= quantity`，且 `shipped_quantity <= outbound_quantity`。

## Customer

租户自己的客户，不是全局通讯录。字段：名称、编码、邮箱、电话、国家、省、城市、地址、状态、备注。

状态：`ACTIVE` / `DISABLED`。

编码：不填则 flush 拿到 id 后写成 `CUS` + 10 位 id，例如 id `25` → `CUS0000000025`。不用 `MAX(code)+1`。`(tenant_id, code)` 唯一，不同企业可以相同编码。创建后编码只读。也可以像供应商一样手填符合规则的编码。

删除：没有任何销售订单引用时允许删除。已被引用只能停用（`40085` `CUSTOMER_IN_USE`）。停用后不能创建新订单（`40119` `CUSTOMER_DISABLED`），历史订单仍可查看。

## 为什么订单保存收货地址快照

客户档案里的地址以后会改。如果订单只存 `customer_id`，再实时读 `Customer.address`，历史订单会被改写。

因此 `SalesOrder` 自己保存当时的：

- `recipient_name`
- `recipient_phone`
- `country_code` / `province` / `city` / `address`

创建时，请求里没传的收货字段用客户档案填一次，然后写在订单列上。之后改客户不影响这张订单。前端选择客户时会把档案填进表单，保存的仍是订单自己的快照。

## SalesOrder

| 字段 | 说明 |
| --- | --- |
| `order_no` | `SO` + 年份 + 6 位 id，例如 id `25` → `SO2026000025`。租户内唯一。全局自增所以不同企业编号可以不连续 |
| `customer_id` / `warehouse_id` | 复合外键，必须属于同一租户 |
| `status` | 见状态机 |
| `source` | `MANUAL` / `AMAZON` / `SHOPIFY` / `TIKTOK` / `OTHER`。只是标记，不接平台 API |
| `external_order_no` | 可空，留给以后的平台订单号。`UNIQUE(tenant_id, source, external_order_no)`。MySQL 把多个 NULL 视为互不相等，手工单可以不填 |
| `currency_code` | 默认 `CNY`。本版不做汇率 |
| 收货字段 | 下单快照 |
| `submitted_at` / `confirmed_at` / `confirmed_by` | 提交与确认 |
| `cancelled_at` / `cancelled_by` / `cancel_reason` | 取消 |
| `created_by` | 创建人 |

金额不落库。明细 `unit_price` 可空，行金额和订单总额在读出时计算。不做税、折扣、运费。

## SalesOrderItem

同一订单同一 SKU 只能一行：`UNIQUE(tenant_id, sales_order_id, sku_id)`。前后端都拒绝重复 SKU。

| 字段 | 说明 |
| --- | --- |
| `quantity` | `> 0` |
| `reserved_quantity` | 当前已预占、尚未正式出库 |
| `outbound_quantity` | 累计仓库已出库 |
| `shipped_quantity` | 累计已交给承运商 |
| `unit_price` | 可空 |

约束：`reserved + outbound <= quantity`，`shipped <= outbound`。买 10、出 6、发 4 之后可以是预占 4、已出库 6、已发货 4。

## 状态机

| 状态 | 中文 |
| --- | --- |
| `DRAFT` | 草稿 |
| `PENDING_CONFIRMATION` | 待确认 |
| `WAITING_OUTBOUND` | 待出库 |
| `PARTIALLY_OUTBOUND` | 部分出库 |
| `OUTBOUNDED` | 已出库 |
| `PARTIALLY_SHIPPED` | 部分发货 |
| `SHIPPED` | 已发货 |
| `COMPLETED` | 已完成（全部签收） |
| `CANCELLED` | 已取消 |

允许：

- `DRAFT` → `PENDING_CONFIRMATION`（提交）
- `PENDING_CONFIRMATION` → `WAITING_OUTBOUND`（确认并预占，并生成第一张出库单）
- `WAITING_OUTBOUND` → `PARTIALLY_OUTBOUND` 或 `OUTBOUNDED`（确认出库）
- `PARTIALLY_OUTBOUND` / `OUTBOUNDED` → `PARTIALLY_SHIPPED` 或 `SHIPPED`（确认发货）
- `PARTIALLY_SHIPPED` → `SHIPPED` → `COMPLETED`（全部签收）
- `DRAFT` / `PENDING_CONFIRMATION` / `WAITING_OUTBOUND` → `CANCELLED`（已有出库数量时不能取消）
- 不能 `PATCH status = COMPLETED`，完成只能由签收结果决定

不允许任意 `PATCH status`。已取消不能再确认。待确认之后不能改客户、仓库、收货信息和明细。没有驳回或撤回提交。

只有草稿可以编辑。改明细时锁订单、校验 SKU 与重复行、删掉旧明细、插入新明细。草稿还没预占，所以不碰库存。

提交前检查：客户启用、仓库启用、至少一条明细、SKU 有效、数量大于 0、收件人和详细地址已填。

## 多 SKU 原子预占

确认整单是一个事务，由 `SalesOrderService.confirm_order()` 提交。`InventoryService.reserve_within_transaction()` 复用 V5 的条件 UPDATE（`quantity - reserved_quantity >= qty`，看 `rowcount`），自己不 commit，也不要求 `inventory:adjust`。对外的 `reserve_inventory()` 仍检查 `inventory:adjust` 并自行提交，库存页面行为不变。

流程：

1. `SELECT FOR UPDATE` 锁订单主行。
2. 确认状态仍是待确认。
3. 按 `sku_id` 升序读取明细。
4. 先收集所有库存不足的 SKU，一次返回列表。
5. 逐个预占。流水 `RESERVE` 指向这张订单。
6. 全部成功后把明细 `reserved_quantity` 写成购买数量，订单改为待出库，写 `confirmed_at` / `confirmed_by`。
7. 一次 commit。

任一 SKU 失败则 rollback。不能出现 SKU A 已预占、SKU B 不足、A 的预占还留着。订单仍是待确认，两边 reserved 不变，没有残留有效流水。

条件 UPDATE 会 `expire_all()`。确认因此先把仓库、单号、明细数量复制出来，预占完成后再重新锁订单写状态。未 flush 的流水对象不受这次过期影响，随最后的 commit 插入。

## 死锁和稳定加锁顺序

两张单可能交叉锁库存：订单 1 先锁 SKU-A 再锁 SKU-B，订单 2 先锁 B 再锁 A，两个事务互相等待。

所有确认和取消都按 `sku_id` 升序处理库存行，锁顺序一致，就不会环路等待。不使用分布式锁。订单主行先锁，库存行后锁。

## 并发确认

两个请求同时确认同一张单：`SELECT FOR UPDATE` 让它们串行。第一个提交后状态已是待出库，第二个看到状态不对，返回非法流转，不会预占第二次。

两张单抢同一库存：各自事务里的条件 UPDATE 保证 `reserved` 不会超过 `quantity`。后拿到锁且可用量不够的那张确认失败并整单回滚。

## 取消与 Confirm / Cancel 竞态

`POST /sales-orders/{id}/cancel`。

- 草稿、待确认：只改订单状态，不动库存。
- 待出库：同一事务里按 `sku_id` 升序调用 `release_within_transaction`，写 `RELEASE` 流水，明细 `reserved_quantity` 归零，再改为已取消。
- 已经取消：`40117` `ORDER_ALREADY_CANCELLED`，不再释放，避免 reserved 变成负数。

确认和取消都先锁订单主行，所以同一张单的两个动作排队。最终只能是一种一致结果：

- 已取消 ⇒ 明细和库存预占都是 0
- 待出库 ⇒ 明细预占等于购买数量，库存预占包含这笔数量

不会出现「订单已取消但库存仍被占」或「待出库但预占已被释放」。释放失败则取消整单回滚。

## API

需要登录和有效 `X-Tenant-ID`。

客户：

- `GET /api/v1/customers`（`customer:read`）
- `POST /api/v1/customers`（`customer:create`）
- `GET /api/v1/customers/{id}`（`customer:read`）
- `PATCH /api/v1/customers/{id}`（`customer:update`）
- `PATCH /api/v1/customers/{id}/status`（`customer:disable`）
- `DELETE /api/v1/customers/{id}`（`customer:delete`）

订单：

- `GET /api/v1/sales-orders`（`order:read`）分页：订单号、平台单号、客户、仓库、SKU 编码、商品名称、状态、来源、创建日期
- `POST /api/v1/sales-orders`（`order:create`）
- `GET /api/v1/sales-orders/{id}`（`order:read`）
- `PATCH /api/v1/sales-orders/{id}`（`order:update`）仅草稿
- `POST /api/v1/sales-orders/{id}/submit`（`order:submit`）
- `POST /api/v1/sales-orders/{id}/confirm`（`order:audit`）
- `POST /api/v1/sales-orders/{id}/cancel`（`order:cancel`）

列表用 SQL 聚合 SKU 种类数、总数量和金额，避免 N+1。详情里的当前库存是辅助数字，不是订单历史。

库存不足：`40070` `INSUFFICIENT_AVAILABLE_INVENTORY`。`data.items` 含 `sku_code`、`requested_quantity`、`available_quantity`。消息形如「SKU000001 可用库存 3，订单需要 5。」

其他常见错误：重复 SKU `40111`，不可编辑 `40112`，缺明细 `40113`，非法流转 `40114`，状态冲突 `40115`，地址不完整 `40116`，已取消 `40117`，客户停用 `40119`，平台单号冲突 `40962`，跨租户订单 `40471`。

可用量提示：`GET /api/v1/inventory/availability?warehouse_id=&sku_ids=`（`inventory:read`）。只给页面提示，确认仍以后端实时库存为准。

## 权限

沿用 `order:*`，不另造 `sales_order:*`。本版补上 `order:update`、`order:submit`。客户与供应商对称：`customer:read/create/update/disable/delete`。

| 角色 | 默认 |
| --- | --- |
| OWNER / ADMIN | 全部 |
| OPERATOR | 订单 read/create/update/submit/cancel，**没有** audit；客户只读 |
| WAREHOUSE | `order:read` |
| VIEWER | `order:read`、`customer:read` |

授权只看 `role_permissions`，不看角色名字。前端按钮隐藏不能代替后端校验。

权限树：订单管理 → 销售订单（查看 / 新建 / 编辑 / 提交 / 审核确认 / 取消）+ 客户管理。

## 前端

菜单「订单管理」：

- `/orders/list` 销售订单
- `/customers` 客户管理（Drawer）
- `/orders/create`、`/orders/:id`、`/orders/:id/edit` 不进菜单

列表复用 V6.1 的 `ListPageContainer` / `AppTable`，不写 `scroll.y`。状态文案在 `packages/shared` 的订单类型里统一。详情用 Timeline：创建、提交、确认并预占、取消。

选择仓库和 SKU 后展示当前可用量。数量超过可用时提示「当前库存可能不足，订单确认时将再次校验。」仍允许保存草稿。

Query Key 带 `tenantId`：`customers`、`sales-orders`、`sales-order`、`sku-inventory`。确认或取消后失效订单列表、详情、库存和流水。
