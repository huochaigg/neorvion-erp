# 订单状态机

业务状态只通过明确 Action：submit / confirm / cancel / 出库 / 发货 / 签收。不允许 `PATCH status`。Router 不直接改 `obj.status`。

原因：状态变迁伴随库存与下游单据。开放任意赋值会绕过预占和幂等。
