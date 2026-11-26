# Copilot 问题中心

记录真实对话里踩到的 Skill / 意图 / 补参 / 生成取消问题，方便后续逐条修。

| 编号 | 状态 | 标题 |
| --- | --- | --- |
| [0001](0001-sku-query-stuck-on-sales-order-review.md) | 待修复 | 案例 A：SKU 销售误选订单审查卡 Pending；案例 B：订单分析后跟进「查询售后记录」因无按单列售后工具而断档 |
| [0002](0002-pending-cancel-too-strict.md) | 待修复 | Pending 取消口令过严，纠正/重开被当成补参 |
| [0003](0003-intent-understanding-improvements.md) | 方案整理 | V15 意图理解架构优化与待解决问题清单 |
| [0004](0004-generation-stuck-cancel-40980.md) | 待修复 | 生成卡住后发「取消」得到 40980，会话 RUNNING 占死 |
| [0005](0005-conversation-create-and-title.md) | 方案整理 | 会话创建立即落库致空会话；标题仅默认「新对话」；手动重命名已有，自动标题与创建幂等待做 |
| [0007](0007-breakpoint-zombie-running-loading.md) | 待修复 | 断点挂起过久后助手消息永久 RUNNING / loading |
| [性能](copilot-chat-performance-investigation.md) | 已修复（待真机确认死循环） | 流式 `# ` 标题使 Markdown 解析死循环；另有 token 全量重渲染与 smooth 滚动 |
