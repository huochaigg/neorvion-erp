# 库存并发

## 为什么库存是 warehouse + sku

同一 SKU 在不同仓库数量独立。台账主键语义是租户 + 仓 + SKU。

## 为什么 available 不存字段

`available = quantity - reserved`。存第三列就要同时维护，容易和前两列打架。展示和校验时计算。

## 为什么订单预占不扣 quantity

货还在仓库里，只是不能卖第二次。预占加 `reserved_quantity`。出库时货才离开。

## 为什么出库 quantity 和 reserved 一起减

出库把「占用中的货」变成「已经发出」。可用量通常不变：实数减少、预占也减少。

## 为什么多 SKU 固定锁顺序

两个事务分别按相反顺序锁 SKU A/B 会死锁。统一 `sku_id` 升序。
