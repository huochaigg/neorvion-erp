# 当前状态

有效里程碑：**V7**。以本文件和当前代码为准。旧版本文档只描述当时范围。

## 已完成

- V3 商品 / SPU / SKU / 类目 / 品牌
- V4 仓库
- V5 库存、流水、条件预占 / 释放、调整锁
- V6 供应商、采购单、采购状态机（审核不改库存）
- V6.1 ERP 布局、Table、主题、中文日期
- V7 客户、销售订单、确认预占、取消释放

## 销售订单

状态：`DRAFT` 草稿、`PENDING_CONFIRMATION` 待确认、`WAITING_OUTBOUND` 待出库、`CANCELLED` 已取消。

库存只在确认进入待出库时预占。`Inventory.quantity` 不变，`reserved_quantity` 增加，可用量下降。流水 `RESERVE`，`reference_type=SALES_ORDER`。

取消待出库时同一事务释放预占并写 `RELEASE`。草稿和待确认取消不动库存。重复取消返回 `ORDER_ALREADY_CANCELLED`。

收货地址存在订单上，是下单快照。来源字段预留平台枚举，不接真实 API。

## V8 可复用

- `reserve_within_transaction` / `release_within_transaction`：共享外层事务，不自己 commit
- 销售订单 `SELECT FOR UPDATE` 串行关键状态
- 多 SKU 按 `sku_id` 升序处理库存
- 订单地址快照、明细 `reserved_quantity` / `shipped_quantity`
- 采购单待收货状态，供以后收货入库

## 明确未做

拣货、正式出库（扣 `quantity`）、发货、物流、订单完成、退货退款、售后、Amazon / Shopify / TikTok 同步、采购收货入库、汇率、税费折扣。
