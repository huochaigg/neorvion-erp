# 库存预占、扣减与释放（已实现）

来源：`services/erp/app/models/inventory.py`、`services/erp/app/services/inventory.py`。库存维度是 Tenant + Warehouse + SKU，不是 SKU 单独一个数字。

## 账面字段

`inventories` 表保存当前账面：

- `quantity`：在库数量
- `reserved_quantity`：已被预占、尚未出库的数量
- 可用库存 = `quantity - reserved_quantity`，不单独落库

## 流水类型（InventoryTransactionType）

INITIALIZE、ADJUST_IN、ADJUST_OUT、RESERVE、RELEASE、INBOUND、OUTBOUND、STOCKTAKE_ADJUSTMENT、TRANSFER_OUT、TRANSFER_IN、RETURN_INBOUND、PURCHASE_RETURN_OUTBOUND。

## 已实现规则

1. 销售确认：写 RESERVE，增加 `reserved_quantity`，不减少 `quantity`。
2. 待出库取消：写 RELEASE，减少 `reserved_quantity`。超量释放会返回 `INSUFFICIENT_RESERVED_INVENTORY`。
3. 销售出库：写 OUTBOUND，同时减少 `quantity` 和 `reserved_quantity`。
4. 采购入库：写 INBOUND，增加 `quantity`。
5. 盘点若与预占冲突，返回 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`。

并发场景下必须锁库存行，禁止先读后写绕过预占。
