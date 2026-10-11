# 销售退货

当前里程碑 **V11**。退货单由需要退货的售后在审核通过时创建。一张售后对应一张退货单。

收到退货不等于入库。只有质量 `GOOD` 的数量默认重新进入普通 `Inventory.quantity`。

## ReturnOrder

编号 `RT` + 年份 + 6 位 id，租户内唯一，不用 `MAX+1`。必须选择当前租户的启用仓库，可以和原履约仓不同，不能跨租户。

状态：`WAITING_RETURN` → `PARTIALLY_RECEIVED` / `RECEIVED` → `PARTIALLY_INBOUNDED` / `INBOUNDED`。

允许分多次收货。累计 `received_quantity` 不能超过 `expected_quantity`。

## ReturnOrderItem

| 字段 | 含义 |
| --- | --- |
| `expected_quantity` | 审核批准后预期客户退回的数量 |
| `received_quantity` | 仓库累计实收 |
| `inbound_quantity` | 已确认进入普通可售库存的数量 |
| `condition` | 质量状态 |

## 商品 condition

| 值 | 中文 | 入库 |
| --- | --- | --- |
| `GOOD` | 正常 | 可以 `inbound_quantity = received_quantity` |
| `DAMAGED` | 损坏 | 可记已收，默认不入普通库存 |
| `UNSELLABLE` | 不可销售 | 不入普通库存 |
| `OTHER` | 其他 | 同残次品，本版不入普通库存 |

当前 `Inventory` 只有 `quantity` / `reserved_quantity`，没有残次品台账。V11 不把库存扩成 WMS 多维度。后续如果需要次品仓，再扩展独立库存状态。

## 为什么入库只增加 quantity

客户退回的是已经正式出库的商品。原订单预占在 V8 确认出库时已经和实际库存一起扣掉。退货回来只补 `quantity`，`reserved_quantity` 不变。

如果把 reserved 加回去，会凭空制造待出库库存。

## RETURN_INBOUND 流水

`change_quantity` 为正。`reference_type = RETURN_ORDER`，`reference_id` 为退货单 id。记录入库前后 `quantity`；reserved 前后相同。

复用 `InventoryService.inbound_within_transaction`，不另写一套库存加法。`tx_type=RETURN_INBOUND`。

## 入库事务

`confirm_return_inbound()` 锁退货单，明细按 `sku_id` 排序，GOOD 的 `received - inbound` 增量入库，残次品 inbound 保持 0。库存、流水、退货明细、退货单状态、售后状态同一事务提交。任一 SKU 失败全部回滚。

已 `INBOUNDED` 再次确认拒绝，库存不能加两次。两个请求同时确认同一张单，只能成功一次。
