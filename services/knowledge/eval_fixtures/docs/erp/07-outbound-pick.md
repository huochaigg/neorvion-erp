# 拣货、部分出库与确认出库（已实现）

来源：`services/erp/app/services/outbound.py`。模块约定：**拣货不扣库存；确认出库才同时减少 quantity 和 reserved。**

## 确认订单后的出库单

销售订单确认成功后，同一事务生成第一张出库单（待拣货）。销售订单进入 `WAITING_OUTBOUND`，库存已经 RESERVE，但出库单此时还没有写 `OUTBOUND`。

## 拣货

`confirm_picking` 只记录本次拣到的数量，**库存不变**。`picked_quantity` 是增量，不是把累计改成最后一次数字。可以分多次拣；全部拣满或明确结束时出库单变为 `PICKED`。

待拣货之外的状态不能再拣。拣货超过剩余计划数量会被拒绝。

## 确认出库

`confirm_outbound` 要求出库单已是 `PICKED`。已确认不能重复扣库存。

确认时调用 `deduct_within_transaction`：`quantity` 和 `reserved` 同时减少，销售明细 `reserved_quantity` 减少、`outbound_quantity` 增加，并按数量推进销售订单履约状态。交给承运商的 `shipped_quantity` 由确认发货维护，本动作不改物流数量。

为什么可用量通常不变：出库前 available = quantity - reserved。两边减去同一个数，差值不变。

## 部分出库与全部出库

部分确认出库后，销售订单进入 `PARTIALLY_OUTBOUND`，此时不能整单取消。全部购买数量离开库存账面后为 `OUTBOUNDED`。部分出库可以继续对剩余数量出库，但不能跳过拣货。
