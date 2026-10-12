# 幂等策略

关键 Action 不允许「重复点击 / 网络重试」产生第二次库存或资金副作用。不强制所有接口都用 `idempotency_key`。

## 总原则

| 手段 | 使用场景 |
| --- | --- |
| 状态机校验 | 已是终态则返回业务冲突，不再改库存 |
| `SELECT FOR UPDATE` | 锁单据主行，Confirm / Cancel 互斥 |
| 条件 UPDATE | 库存预占 / 扣减，影响行数为 0 则失败回滚 |
| 唯一约束 | 租户内单号、`(tenant, warehouse, sku)` 库存行 |
| `idempotency_key` | 异步任务投递等易重复的创建 |

## 当前 Action

| Action | 如何保证 |
| --- | --- |
| confirm order | 锁订单；仅待确认可预占；重复 confirm 状态冲突 |
| cancel order | 锁订单；已出库不可取消；重复 cancel 冲突；释放用条件 UPDATE |
| approve purchase | 条件 UPDATE 状态；审核不改库存 |
| confirm purchase receipt | 草稿才入库；`PURCHASE_RECEIPT_ALREADY_CONFIRMED` |
| confirm outbound | 拣货完成后才扣减；已确认拒绝第二次 |
| confirm shipment | 草稿才进入在途；不改库存 |
| deliver shipment | 已签收拒绝；全部签收才把销售单标完成 |
| confirm stocktake | 按差异调整一次；已确认拒绝 |
| confirm transfer outbound / receive | 状态机 + 扣 available / 加 quantity；在途后才能调入 |
| confirm return inbound | `RETURN_ALREADY_INBOUNDED`；只加 quantity |
| confirm purchase return outbound | `PURCHASE_RETURN_OUTBOUND_ALREADY_CONFIRMED` |
| confirm refund | 失败记录保留，重试新建一行；成功后累计金额校验 |
| retry task | 锁任务行；把状态收口到 `QUEUED` 再投递，避免双 PENDING |

前端重复请求仍然可能看到 400 状态冲突，这是预期，不是第二次成功扣减。
