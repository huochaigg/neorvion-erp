---
name: order-status-explanation
description: Explain the current status and status meaning of one existing sales order using read-only ERP evidence. Use for status explanation, not full anomaly review.
metadata:
  neorvion-category: sales-status
  neorvion-risk: read-only
  neorvion-resource-triggers: 状态含义,status meaning,解释
---

# 销售订单状态解释

使用订单主键调用 `get_sales_order`，只解释工具返回的当前状态及其含义。
需要状态口径时读取 [状态说明](references/status-notes.md)。
不得修改、审批、发货或退款；不得把状态解释成已经发生的履约动作。
