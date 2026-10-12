# 销售履约

确认 → 预占 → 拣货（不扣库存）→ 确认出库（扣 quantity+reserved）→ 物流单（不改库存，只加 shipped）→ 签收完成。

V8 的仓库出库和 V9 的物流发货拆开：`OUTBOUNDED` 不是 `SHIPPED`。
