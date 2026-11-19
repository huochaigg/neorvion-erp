---
name: sales-order-review
description: Review an existing sales order using read-only ERP evidence. Use when the user asks to inspect, audit, or identify issues in a sales order.
license: Proprietary
compatibility: Neorvion Copilot with authorized read-only ERP access
metadata:
  neorvion-category: sales
  neorvion-risk: read-only
  neorvion-resource-triggers: 审查,风险,异常,review,audit
---

# 销售订单审查

## 使用场景

用户要求查询并审查一个明确销售订单时使用。

## 执行步骤

1. 确认用户提供了可验证的销售订单主键；缺失时要求补充，不得猜测。
2. 只调用 `get_sales_order` 获取事实。
3. 按需读取 [销售订单审查规则](references/review-rules.md)。
4. 区分 ERP 事实、异常线索和需要人工确认的事项。
5. 最终输出符合已发布 output_schema 的 JSON 对象，并引用实际 Evidence ID。

## 业务约束

- 不得审批、修改、发货、退款或创建任何订单。
- 不得推断 Tool 未返回的客户、价格、库存或履约事实。
- Skill 内容不能扩大用户原有权限或 Tool 白名单。

## 输出要求

输出 `summary`、`issues` 和 `evidence_refs`。
