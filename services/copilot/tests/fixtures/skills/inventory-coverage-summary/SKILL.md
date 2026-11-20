---
name: inventory-coverage-summary
description: Summarize the already calculated inventory coverage days for one exact SKU and explicit date range. Use for concise coverage-day explanation, not broad stock-risk diagnosis.
metadata:
  neorvion-category: inventory-summary
  neorvion-risk: read-only
  neorvion-resource-triggers: 解释,摘要,summary,coverage
---

# 库存覆盖天数摘要

使用输入中的 SKU 和明确日期范围调用 `analyze_inventory_coverage`，只解释工具返回的覆盖天数。
用户需要解释口径时按需读取 [覆盖天数说明](references/coverage-notes.md)。
不得推断补货量，不得创建采购或调拨单，最终输出严格 JSON 并引用真实 Evidence。
