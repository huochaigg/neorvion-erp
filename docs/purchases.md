# 采购管理

当前里程碑 **V6**。采购单表示企业向供应商采购一批 SKU，是计划而不是库存事实。

```text
创建供应商 → 创建采购单（草稿）→ 提交审核 → 审核通过进入待收货
```

审核通过 **不会** 增加 `inventory.quantity`。货可能少到、晚到或根本没到。库存增加留给后续收货 / 入库版本，那时才写 `received_quantity` 并生成入库流水。

本版 **不** 开发：采购收货、采购入库、部分收货、库存增加、采购退货、采购付款、财务结算、销售订单、物流。

## 为什么采购和库存必须分开

采购 100 件只表示「计划买 100」。仓库里现在有没有这 100 件，要等收货确认。如果审核通过就改库存：

- 供应商只发了 80，账面已经多了 20
- 审核人通过的是计划，不是实物

所以 V6 采购单只改自己的状态和明细。`Inventory` 一行都不碰。

后续收货版本建议：

```text
收货数量写入 purchase_order_items.received_quantity
同一事务：Inventory.quantity += 实收
同一事务：插入 InventoryTransaction type=INBOUND
约束：0 <= received_quantity <= quantity
```

V6 提前把 `received_quantity` 做成默认 0，避免下一版再改表结构。

## 供应商 Supplier

迁移：`backend/alembic/versions/20261005_0011_create_purchase_tables.py`

| 列 | 说明 |
| --- | --- |
| `id` / `tenant_id` | 主键 + 租户 |
| `name` | 名称 |
| `code` | 租户内唯一。可空提交，flush 后写成 `SUP` + 10 位 id |
| `contact_*` / 地址 | 可空 |
| `status` | `ACTIVE` / `DISABLED` |
| `remark` | 可空 |

编码不要用 `MAX(code)+1`：删除后会复用号段，并发也不安全。创建后 PATCH 不提交 `code`，界面默认只读。

禁用供应商：不能再创建新采购单，也不能把已有草稿的供应商改成该停用供应商。历史采购单保留，不要因为停用去改旧单状态。

删除：没有任何采购单引用时允许物理删除；已被引用只能停用（`40081` `SUPPLIER_IN_USE`）。

不同租户可以有相同 `code`。A 企业不能用 `supplier_id` 引用 B 企业供应商。

## 采购单 PurchaseOrder

| 列 | 说明 |
| --- | --- |
| `order_no` | `PO` + 年份 + 6 位 id。flush 拿 id 后再写，租户内唯一 |
| `supplier_id` / `warehouse_id` | 复合外键保证同租户 |
| `status` | 见状态机 |
| `expected_arrival_date` | 可空 |
| `submitted_at` / `approved_at` / `approved_by` | 提交与审核 |
| `rejected_at` / `rejected_by` / `reject_reason` | 驳回 |
| `cancelled_at` / `cancelled_by` / `cancel_reason` | 取消 |
| `created_by` | 创建人，用户删除时限制 |

单号同样不用 `MAX(order_no)+1`。`id = 25` 且当前年 2026 时得到 `PO2026000025`。如果以后要租户独立连续流水，再加 sequence 表。

## 采购明细 PurchaseOrderItem

| 列 | 说明 |
| --- | --- |
| `sku_id` | 复合外键保证 SKU 属于本租户 |
| `quantity` | 采购数量，必须 `> 0` |
| `unit_price` | 可空 `Numeric(12,2)` |
| `received_quantity` | V6 恒为 0；`0 <= received_quantity <= quantity` |
| `remark` | 可空 |

`UNIQUE(tenant_id, purchase_order_id, sku_id)`：同一张单同一个 SKU 只能一行。需要同一 SKU 不同单价多行时以后再拆。

金额不落库：

- `line_amount = quantity * unit_price`（没填单价则为空）
- `total_amount` = 有单价的行合计；全部没填价格时接口返回 `null`，前端显示 `-`

税率、币种、折扣、运费不在本版。

## 状态机

不保留 `APPROVED` 中间态。审核通过同一次条件 UPDATE 直接进入待收货，避免多一个几乎立刻被覆盖的状态。

```text
DRAFT ──submit──► PENDING_APPROVAL ──approve──► WAITING_RECEIPT
  │                      │
  │                      └──reject──► REJECTED ──submit──► PENDING_APPROVAL
  │                      │
  └──cancel──► CANCELLED ◄── cancel ◄── REJECTED / PENDING_APPROVAL
```

| 当前 | 可转到 |
| --- | --- |
| DRAFT | PENDING_APPROVAL、CANCELLED |
| PENDING_APPROVAL | WAITING_RECEIPT、REJECTED、CANCELLED |
| REJECTED | PENDING_APPROVAL、CANCELLED |
| WAITING_RECEIPT | 无（V6 不允许取消） |
| CANCELLED | 无 |

不允许：`CANCELLED → APPROVED`、`WAITING_RECEIPT → DRAFT`。

实现集中在 `PurchaseOrderStateMachine` 风格模块 `app/services/purchase_state.py`：`ALLOWED_TRANSITIONS` + `can_transition()` / `require_transition()`。接口里不要再散落 `if status == ...`。

可编辑核心字段（供应商、仓库、预计到货、备注、明细）：仅 `DRAFT`、`REJECTED`。

提交审核：`DRAFT` 或 `REJECTED`，且至少一条明细，供应商/仓库/SKU 仍有效。

待收货后不能改 SKU 和数量。审核人看过的内容如果被改掉，审核结果就没有意义。正式改单要以后做采购变更流程。

V6 禁止取消 `WAITING_RECEIPT`：审核通过可能已经通知供应商。以后可以做关闭 / 作废。

## 创建事务

```text
BEGIN
校验供应商属于本租户且 ACTIVE
校验仓库属于本租户且 ACTIVE
一次性校验全部 SKU 属于本租户且 ACTIVE，禁止重复 sku_id
INSERT purchase_orders（此时 order_no 为空）
FLUSH 拿到 id
写入 PO{年}{id:06d}
INSERT 全部 purchase_order_items
COMMIT
```

任一行失败 `ROLLBACK`。不能留下「主表在、明细不完整」。Repository 不 `commit`，由 Service 提交。

## 编辑草稿：整体替换明细

不要拆一堆增删改明细接口。当前复杂度下整表替换更不容易漏：

```text
BEGIN
SELECT ... FOR UPDATE 锁采购单
校验状态可编辑
校验新明细 SKU
DELETE 旧明细
INSERT 新明细
COMMIT
```

## 并发审核

两个管理员同时点通过和驳回，不能互相覆盖。

状态流转使用条件 UPDATE，而不是先读再无条件写：

```sql
UPDATE purchase_orders
SET status = 'WAITING_RECEIPT', approved_at = ..., approved_by = ...
WHERE id = :id
  AND tenant_id = :tenant_id
  AND status = 'PENDING_APPROVAL'
```

`rowcount == 0` 表示别人已经改过，返回 `40095` `PURCHASE_ORDER_STATE_CONFLICT`。

和 `SELECT FOR UPDATE` 的差别：

- 条件 UPDATE：适合「只改状态、冲突就失败」的短事务
- FOR UPDATE：适合编辑草稿时锁主表，再删插多行明细

复杂审核如果以后要同时写审批日志、通知，可以在同一事务里 FOR UPDATE 再改状态。V6 审核路径用条件 UPDATE 就够。

## 查询

列表默认 `created_at DESC`。筛选：单号、供应商、仓库、SKU、状态、创建时间、预计到货、创建人。

列表用 JOIN + `COUNT(item)` / `SUM(quantity)` 聚合，不要把全部明细加载到 Python 再 sum。详情用 `selectinload` 一次带出明细、SKU、商品。

## API

需要登录和有效 `X-Tenant-ID`。

供应商：

- `GET /api/v1/suppliers`（`supplier:read`）`q` / `status` / `country_code`
- `POST /api/v1/suppliers`（`supplier:create`）
- `GET /api/v1/suppliers/{id}`（`supplier:read`）
- `PATCH /api/v1/suppliers/{id}`（`supplier:update`）不改 code
- `PATCH /api/v1/suppliers/{id}/status`（`supplier:disable`）
- `DELETE /api/v1/suppliers/{id}`（`supplier:delete`）

采购单：

- `GET /api/v1/purchase-orders`（`purchase:read`）
- `POST /api/v1/purchase-orders`（`purchase:create`）
- `GET /api/v1/purchase-orders/{id}`（`purchase:read`）
- `PATCH /api/v1/purchase-orders/{id}`（`purchase:update`）
- `POST /api/v1/purchase-orders/{id}/submit`（`purchase:submit`）
- `POST /api/v1/purchase-orders/{id}/approve`（`purchase:audit`）
- `POST /api/v1/purchase-orders/{id}/reject`（`purchase:audit`）body：`reason`
- `POST /api/v1/purchase-orders/{id}/cancel`（`purchase:cancel`）

submit / approve / reject / cancel 是明确业务动作，不塞进通用 PATCH。

错误码（常见）：供应商 `40080` 状态不合法、`40081` 使用中、`40460` 不存在、`40960` 编码冲突。采购单 `40090` 非法流转、`40091` 不可编辑、`40093` SKU 重复、`40095` 状态冲突、`40470` 不存在。

## 权限

| 编码 | 用途 |
| --- | --- |
| `purchase:read` | 列表 / 详情 / 菜单 |
| `purchase:create` | 新建草稿 |
| `purchase:update` | 编辑草稿或驳回单 |
| `purchase:submit` | 提交 / 重新提交 |
| `purchase:audit` | 通过 / 驳回 |
| `purchase:cancel` | 取消 |
| `supplier:read` | 供应商列表 |
| `supplier:create` / `update` / `disable` / `delete` | 供应商写操作 |

OWNER / ADMIN：全部。OPERATOR：供应商只读 + 采购 read/create/update/submit/cancel，**没有** audit。WAREHOUSE / VIEWER：供应商与采购只读。

权限树：采购管理 → 采购单（查看/新建/编辑/提交审核/审核/取消）+ 供应商管理（查看/新建/编辑/启用禁用/删除）。

已被采购单引用的仓库、SKU 不能删除（与库存引用相同的 `WAREHOUSE_IN_USE` / `SKU_IN_USE`）。

## 前端

菜单「采购管理」：

- `/purchases/list` 列表
- `/suppliers` 供应商
- `/purchases/create`、`/purchases/:id`、`/purchases/:id/edit` 不进菜单

详情按状态 + 权限显示编辑、提交、通过、驳回、取消。待收货只展示状态，本版没有收货按钮。编辑 URL 在不可编辑状态会跳详情；后端仍拒绝保存。

SKU 下拉远程搜索，不要一次拉全表。前端重复选择同一 SKU 时合并数量；后端 UNIQUE 是最终保证。

Query Key：`['tenant', tenantId, 'suppliers', params]`、`['tenant', tenantId, 'purchase-orders', params]`、`['tenant', tenantId, 'purchase-order', id]`。状态流转后 invalidate。切租户后 `/purchases/:id` 回到列表。
