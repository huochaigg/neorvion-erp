# 当前状态

有效里程碑：**V9**。以本文件和当前代码为准。旧版本文档只描述当时范围。

## 已完成

- V3 商品 / SPU / SKU / 类目 / 品牌
- V4 仓库
- V5 库存、流水、条件预占 / 释放 / 扣减预占、调整锁
- V6 供应商、采购单、采购状态机（审核不改库存）
- V6.1 ERP 布局、Table、主题、中文日期
- V7 客户、销售订单、确认预占、取消释放
- V8 采购收货入库、销售拣货与确认出库、部分收货 / 部分出库
- V9 物流商、物流单、确认发货、手工轨迹、签收、销售订单完成

## 采购

采购 → 收货 → 入库。

审核通过仍不增加库存。库存增加只发生在收货单确认：`Inventory.quantity` 增加，`reserved_quantity` 不变，流水 `INBOUND`。

## 销售

订单 → 预占 → 拣货 → 出库 → 物流发货 → 签收 → 完成。

| 步骤 | Inventory.quantity | reserved_quantity | 订单数量字段 |
| --- | --- | --- | --- |
| 确认订单 | 不变 | 增加 | `reserved_quantity` 增加 |
| 确认出库 | 减少 | 减少 | `outbound_quantity` 增加，`reserved_quantity` 减少 |
| 确认发货 | 不变 | 不变 | `shipped_quantity` 增加 |
| 签收 | 不变 | 不变 | 全部签收后订单 `COMPLETED` |

`SalesOrderItem.quantity` 是订单数量。`reserved_quantity` 是尚未出库的预占。`outbound_quantity` 是累计仓库出库。`shipped_quantity` 是累计交给承运商。约束是 `reserved + outbound <= quantity`，且 `shipped <= outbound`。

V8 曾用 `SHIPPED` 表示已出库。V9 把仓库出库改成 `PARTIALLY_OUTBOUND` / `OUTBOUNDED`，把 `PARTIALLY_SHIPPED` / `SHIPPED` 留给物流。

有正式出库后不能取消整张销售订单。

## 库存字段

| 字段 | 含义 |
| --- | --- |
| `quantity` | 仓库里的实际数量 |
| `reserved_quantity` | 已被订单占用、尚未出库 |
| `available_quantity` | 不入库，等于 `quantity - reserved_quantity` |

## 下一版可复用

- `inbound_within_transaction` / `deduct_within_transaction`
- `reserve_within_transaction` / `release_within_transaction`
- 收货、出库、发货按 `sku_id` 升序加锁
- `ShipmentService.confirm_shipment` / `mark_delivered`：不改库存，只推进履约状态
- Carrier 档案和手工轨迹模型，以后接真实物流 API 仍写入同一张表

## 明确未做

真实承运商 API、电子面单、自动轨迹、Amazon / Shopify / TikTok 同步、退货、退款、售后、财务结算、库存盘点、调拨、AI Agent。
