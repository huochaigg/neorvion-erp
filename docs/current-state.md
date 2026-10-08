# 当前状态

有效里程碑：**V8**。以本文件和当前代码为准。旧版本文档只描述当时范围。

## 已完成

- V3 商品 / SPU / SKU / 类目 / 品牌
- V4 仓库
- V5 库存、流水、条件预占 / 释放 / 扣减预占、调整锁
- V6 供应商、采购单、采购状态机（审核不改库存）
- V6.1 ERP 布局、Table、主题、中文日期
- V7 客户、销售订单、确认预占、取消释放
- V8 采购收货入库、销售拣货与确认出库、部分收货 / 部分出库

## 采购

状态在草稿、待审核、已驳回、已取消之外，还有 `WAITING_RECEIPT` 待收货、`PARTIALLY_RECEIVED` 部分收货、`RECEIVED` 已收货。

审核通过仍不增加库存。库存增加只发生在收货单确认：`Inventory.quantity` 增加，`reserved_quantity` 不变，流水 `INBOUND`，`reference_type=PURCHASE_RECEIPT`。

`PurchaseOrderItem.quantity` 是计划采购量，`received_quantity` 是累计已入库量，且 `received_quantity <= quantity`。

## 销售

状态在草稿、待确认、待出库、已取消之外，还有 `PARTIALLY_SHIPPED` 部分出库、`SHIPPED` 已出库。

确认订单：`reserved_quantity` 增加，`quantity` 不变，流水 `RESERVE`。同一事务生成第一张出库单。拣货不改库存。确认出库：`quantity` 和 `reserved_quantity` 同时减少，流水 `OUTBOUND`，`reference_type=OUTBOUND_ORDER`。可用量在这批已预占商品出库时通常不变。

`SalesOrderItem.quantity` 是订单数量。`reserved_quantity` 是尚未出库的预占。`shipped_quantity` 是累计已出库。约束是 `reserved + shipped <= quantity`，不再要求已出库小于等于当前预占。

有正式出库后不能取消整张销售订单。待出库且尚未出库时取消，会作废未完成出库单并释放预占。

## 库存字段

| 字段 | 含义 |
| --- | --- |
| `quantity` | 仓库里的实际数量 |
| `reserved_quantity` | 已被订单占用、尚未出库 |
| `available_quantity` | 不入库，等于 `quantity - reserved_quantity` |

## 下一版可复用

- `inbound_within_transaction` / `deduct_within_transaction`：共享外层事务，不自己 commit
- `reserve_within_transaction` / `release_within_transaction`
- 收货、出库按 `sku_id` 升序锁库存
- 采购收货与销售出库单据、状态机和权限

## 明确未做

物流、运单、轨迹、签收、采购退货、销售退货、退款、售后、财务结算、真实 Amazon / Shopify / TikTok 同步、库存盘点、调拨。
