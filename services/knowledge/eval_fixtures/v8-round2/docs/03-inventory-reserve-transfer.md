# 库存、预占、释放与调拨

库存维度是 `Tenant + Warehouse + SKU`，不是 SKU 单独一个数字。同一 SKU 在深圳仓、广州仓可以有完全不同的数量。唯一约束是 `UNIQUE(tenant_id, warehouse_id, sku_id)`。

## 三个数量

| 字段 | 存库 | 含义 |
| --- | --- | --- |
| `quantity` | 是 | 实际账面库存，货还在仓里的数字 |
| `reserved_quantity` | 是 | 已被业务预占、尚未正式出库 |
| `available_quantity` | 否 | `quantity - reserved_quantity`，查询时计算 |

不把可用库存存成第三列，避免三个数字互相打架。数据库 CHECK 与 Service 双重校验：

- `quantity >= 0`
- `reserved_quantity >= 0`
- `reserved_quantity <= quantity`

MySQL 8.0.16+ 会执行 CHECK。即便如此，业务校验仍必须做。

## 台账与流水

`Inventory` 是当前状态。`InventoryTransaction` 是变化历史，只追加，普通业务不允许改或删。如果盘点把 100 错加到 120，不要改历史，再做一笔调整回到 100。

库存数字和流水必须在同一个事务里提交：锁住或条件更新库存行，修改 `Inventory`，插入流水，然后提交。任一步失败回滚。不能先提交库存再插流水。

`InventoryTransactionType` 当前已写入的类型：

| 类型 | 英文标识 | 谁写入 |
| --- | --- | --- |
| 初始化 | `INITIALIZE` | 库存初始化 |
| 盘盈 / 盘亏调整 | `ADJUST_IN` / `ADJUST_OUT` | 库存调整 |
| 预占 / 释放 | `RESERVE` / `RELEASE` | 销售确认 / 取消待出库 |
| 采购入库 | `INBOUND` | 确认收货 |
| 销售出库 | `OUTBOUND` | 确认出库 |
| 盘点调整 | `STOCKTAKE_ADJUSTMENT` | 确认盘点 |
| 调出 / 调入 | `TRANSFER_OUT` / `TRANSFER_IN` | 调拨确认调出 / 调入 |
| 销售退货入库 | `RETURN_INBOUND` | 退货确认入库 |
| 采购退货出库 | `PURCHASE_RETURN_OUTBOUND` | 确认采购退货出库 |

`reserve` / `release` / `deduct_within_transaction` / `inbound_within_transaction` / `apply_delta_within_transaction` / `deduct_available_within_transaction` 由业务 Service 在同一事务里调用。ERP 菜单没有「手动预占」按钮。

## 预占、释放与可用不足

销售订单确认调用预占：可用不足则 `INSUFFICIENT_AVAILABLE_INVENTORY`。待出库整单取消调用释放：释放数量超过 `reserved_quantity` 则 `INSUFFICIENT_RESERVED_INVENTORY`。

两个码都带 `INSUFFICIENT_`，路径不同：

| 错误码 | 典型场景 | 卡住的数字 |
| --- | --- | --- |
| `INSUFFICIENT_AVAILABLE_INVENTORY` | 销售确认、调拨调出、采购退货出库、可用不足的调整 | `quantity - reserved` |
| `INSUFFICIENT_RESERVED_INVENTORY` | 释放预占超过账面预占 | `reserved_quantity` |
| `OUTBOUND_EXCEEDS_RESERVED` | 销售出库超过该订单已预占 | 订单明细预占 |
| `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY` | 盘点要把实际库存调到低于现有预占 | `reserved_quantity <= quantity` |

测试 `test_inventory.py` 断言释放超额是 `INSUFFICIENT_RESERVED_INVENTORY`。测试 `test_stocktake.py` 断言盘点冲突是 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`。这两个码不能互换，也不能写成出库超额的 `OUTBOUND_EXCEEDS_RESERVED`。

库存行带乐观锁 `version`。条件 UPDATE 保证不能让 `quantity < reserved`。明细按 `sku_id` 排序后再处理库存，降低死锁概率。Repository 不自行 commit。

## 盘点

`StocktakeOrderStatus`：创建后本版直接进入 `COUNTING`（`DRAFT` 保留给以后「先建任务再开始」）→ `PENDING_CONFIRMATION` → `CONFIRMED`。确认前可取消。

盘点中可填写实盘数量；不锁库存行，避免盘点持续几小时占着数据库锁。创建时只拍账面快照，确认时才按差异调整 `Inventory`，流水类型 `STOCKTAKE_ADJUSTMENT`。

范围：`ALL` 或 `SELECTED_SKU`。权限：`stocktake:read/create/update/submit/confirm/cancel`。

确认后如果调整结果会打破 `reserved_quantity <= quantity`，失败码是 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`。盘点不能悄悄释放销售预占。

## 调拨状态机

调拨是同一租户两个启用仓库之间移动库存。不支持跨租户；跨公司应走采购或销售。源仓不能等于目标仓。

`StockTransferStatus`：

| 状态 | 英文标识 | 库存 | 能否普通取消 |
| --- | --- | --- | --- |
| 草稿 | `DRAFT` | 不改。库存不足也可以先保存 | 可以 |
| 待调出 | `PENDING_OUTBOUND` | 核心字段锁定；确认调出才扣源仓 | 可以 |
| 在途 | `IN_TRANSIT` | 源仓已扣，目标仓尚未增加 | 不能 |
| 已完成 | `COMPLETED` | 目标仓已增加 | 终态 |
| 已取消 | `CANCELLED` | 仅草稿和待调出 | 终态 |

提交调拨：`DRAFT` → `PENDING_OUTBOUND`。代码注释写明仍然不改库存。因此调拨草稿和调拨提交都还没有改库存数量。不要把它说成确认销售订单那样的预占。

确认调出：源仓 `quantity` 减少，写 `TRANSFER_OUT`。目标仓不变。货物已离开源仓，尚未进入目标仓。第一版不建独立 `inventory_in_transit` 表，用 `IN_TRANSIT` + `outbound_quantity` 表示。

确认调入：目标仓 `quantity` 增加，写 `TRANSFER_IN`。`received_quantity` 默认等于 `outbound_quantity`，暂不处理运输损耗。在途后不能普通取消；撤回应创建反向调拨。

调拨单号：`TR` + 年份 + 6 位 id。权限：`stock_transfer:read/create/update/submit/outbound/receive/cancel`。调出和调入单独授权。不要开放 `PATCH status`。

## 调拨只能动 available

账面 100、预占 80、可用 20。那 80 已经卖给销售订单。最多只能调 20。调拨不能释放源仓预占，也不能给目标仓增加预占。

确认调出使用 `InventoryService.deduct_available_within_transaction`：条件 UPDATE 要求 `quantity - reserved >= 调拨数量`。不足时仍是 `INSUFFICIENT_AVAILABLE_INVENTORY`。测试 `test_stock_transfer.py` 断言该码。

目标仓第一次调入某 SKU 时，复用收货入库的安全创建：先插入 `quantity=0`，撞上唯一约束只回滚保存点，再增加数量。

重复确认调出 → `STOCK_TRANSFER_ALREADY_OUTBOUND`。重复确认调入 → `STOCK_TRANSFER_ALREADY_RECEIVED`。

调出：调拨单、明细、源仓库存、`TRANSFER_OUT` 流水同一事务。任一 SKU 不足整单回滚。调入同理。

## `PENDING_OUTBOUND` 不是销售待出库

销售订单确认后的待出库英文是 `WAITING_OUTBOUND`，此时已经预占。调拨提交后的待调出英文是 `PENDING_OUTBOUND`，此时尚未扣库存。采购退货审核通过后也进入名为 `WAITING_OUTBOUND` 的状态，那是等待退给供应商，同样还没有扣库存，扣减发生在确认采购退货出库。

三个「等待出库」不能共用一条库存规则。

## 初始化与调整权限

`inventory:read` 查看台账。`inventory:initialize` 初始化。`inventory:adjust` 调整。`inventory:transaction:read` 看流水。`inventory:inbound` / `inventory:outbound` 是预留编码，收货和销售出库的业务确认不要求再同时拥有它们。

## 流水字段

| 列 | 含义 |
| --- | --- |
| `type` | `InventoryTransactionType` |
| `change_quantity` | 实际库存变化；预占和释放为 0 |
| `before_quantity` / `after_quantity` | 变化前后实际库存 |
| `before_reserved_quantity` / `after_reserved_quantity` | 变化前后预占 |
| `reference_type` / `reference_id` | 关联单据 |
| `remark` | 备注，销售预占会写订单号 |
| `operator_user_id` | 操作人，用户删除后 SET NULL |
| `created_at` | 流水时间，无 `updated_at` |

预占：`change_quantity = 0`，`after_reserved` 增加。释放相反。销售出库：`change_quantity` 为负，实际和预占同时下降。采购入库：`change_quantity` 为正，预占前后相等。

## 仓库与 SKU 必须启用

库存行挂在启用中的仓库和有效 SKU 上。停用仓库后不能再对该仓做入库、出库、调拨、盘点确认等改库存动作。查询历史台账仍按 `tenant_id + warehouse_id + sku_id` 读，不因为仓库停用而删除行。

初始化给某仓某 SKU 写第一笔 `quantity`，流水 `INITIALIZE`。调整用 `ADJUST_IN` / `ADJUST_OUT`。调整同样不能打破 `reserved_quantity <= quantity`，也不能把可用调成负数。

## 调拨提交之后还能改什么

`PENDING_OUTBOUND` 锁定核心字段：源仓、目标仓、明细数量。备注类字段是否可改以当前 Service 为准，库存一定还没动。确认调出后进入 `IN_TRANSIT`，源仓 `quantity` 已减少，目标仓仍没有这批货。此时账面总和小于调出前，差额就是在途。第一版用状态和 `outbound_quantity` 表达在途，不另建在途表。

确认调入默认按调出数量加到目标仓。本版不在调入时填损耗。若实际少到，需要后续用库存调整或反向调拨处理，不要在本调拨单上改写已发生的 `TRANSFER_OUT`。

## 条件 UPDATE 与乐观锁

预占、扣可用、出库扣减都用带条件的 UPDATE，看 `rowcount`。可用不足时 `rowcount = 0`，对应 `INSUFFICIENT_AVAILABLE_INVENTORY`。不要先读出数字再在 Python 里相减后写回：两个请求会读到同一快照。

库存行有 `version`。条件失败时整单回滚。明细按 `sku_id` 排序后再锁，降低销售出库、调拨调出、采购退货出库交叉锁的死锁概率。Repository 不自行 commit，由调用方业务事务提交。

## 盘点差异加在当前账面

盘点确认走 `apply_delta_within_transaction`。创建时的 `system_quantity` 只用于计算差异，不用于覆盖当前 `quantity`。期间若采购入库已经加过库存，确认盘点仍只加减差异。

盘亏后如果 `quantity` 将低于 `reserved_quantity`，失败码是 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`，不是释放路径的 `INSUFFICIENT_RESERVED_INVENTORY`。盘点文档与物流文档展开状态机；库存文档只保留与三个数量有关的约束。

调拨源仓与目标仓都必须启用。停用仓调拨失败业务码 `40097`，中文「只能使用启用中的仓库调拨」。这与销售订单 `WAREHOUSE_DISABLED` 是同一类仓库启用校验，但是否带 `data.error` 以各 Service 为准。

## 在途之后只能反向调拨

重复确认调出：`STOCK_TRANSFER_ALREADY_OUTBOUND`。重复确认调入：`STOCK_TRANSFER_ALREADY_RECEIVED`。进入 `IN_TRANSIT` 后不能普通取消，因为源仓 `quantity` 已减少。要把货调回去，应新建一张方向相反的调拨单，而不是改写已发生的 `TRANSFER_OUT`。

调拨确认调出失败时整单回滚，源仓数字不变。可用 20、明细却写 30，错误码仍是 `INSUFFICIENT_AVAILABLE_INVENTORY`。不要把它解释成销售出库超额：调拨从未预占过这 30 件。

源仓等于目标仓必须拒绝。跨租户没有调拨接口。跨公司应走销售或采购，而不是调拨。

调拨单号前缀 `TR`。权限拆开：`stock_transfer:submit` 只进入 `PENDING_OUTBOUND`，`stock_transfer:outbound` 才扣源仓，`stock_transfer:receive` 才加目标仓。不要用销售的 `order:audit` 或 `outbound:confirm` 去描述调拨。

