# 库存预占、扣减与释放（已实现）

来源：`services/erp/app/models/inventory.py`、`services/erp/app/services/inventory.py`。库存维度是 **Tenant + Warehouse + SKU**，不是 SKU 单独一个数字，也不是落在 SPU。

## 账面字段

`inventories` 表保存当前账面：

- `quantity`：在库数量
- `reserved_quantity`：已被预占、尚未出库的数量
- **没有单独的可用库存列。** 可用库存 = `quantity - reserved_quantity`

约束：`quantity >= 0`，`reserved_quantity >= 0`，且 `reserved_quantity <= quantity`。并发场景必须锁库存行，禁止先读后写绕过预占。

## 流水类型（InventoryTransactionType）

INITIALIZE、ADJUST_IN、ADJUST_OUT、RESERVE、RELEASE、INBOUND、OUTBOUND、STOCKTAKE_ADJUSTMENT、TRANSFER_OUT、TRANSFER_IN、RETURN_INBOUND、PURCHASE_RETURN_OUTBOUND。

销售预占流水用 `reference_type = SALES_ORDER` 区分来源订单。

## 已实现规则

1. **销售确认**：写 `RESERVE`，增加 `reserved_quantity`，不减少 `quantity`。
2. **待出库取消**：写 `RELEASE`，减少 `reserved_quantity`。超量释放返回 `INSUFFICIENT_RESERVED_INVENTORY`。
3. **销售出库（确认出库）**：写 `OUTBOUND`，同时减少 `quantity` 和 `reserved_quantity`。拣货阶段不写 OUTBOUND。
4. **采购入库（确认收货）**：写 `INBOUND`，只增加 `quantity`，不改 `reserved_quantity`。
5. **盘点若与预占冲突**：返回 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`。
6. **调拨**：源仓 `TRANSFER_OUT`，目标仓 `TRANSFER_IN`。
7. **售后退货入库**：写 `RETURN_INBOUND`。
8. **采购退货出库**：写 `PURCHASE_RETURN_OUTBOUND`。

## 可用量在确认与出库时如何变化

确认 2 件后：若原 `quantity=10`，则 `reserved_quantity` 变为 2，可用变为 8，`quantity` 仍为 10。

确认出库 2 件后：`quantity` 与 `reserved_quantity` 同时减 2。出库前可用 = quantity - reserved；两边减去同一个数，**可用量通常不变**，因为这批货出库前已经被预占，不算可售。
