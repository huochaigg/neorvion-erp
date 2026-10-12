# Agent 接入准备

Core V1 只准备边界，不开发 Copilot。

## 只读 Tool 可包装的 API

商品查询、库存查询、销售订单查询、采购查询、售后查询、Analytics、Event、Task。这些已经是租户隔离 + RBAC 的 HTTP API。

## 写操作边界

```text
Agent → Tool → ERP API / Application Service
      → TenantContext → RBAC → 状态机 / 事务 / 审计 → MySQL
```

禁止：

- Agent 直连 ERP MySQL 执行 UPDATE
- 绕过权限、状态机、库存锁、Outbox
- 把库存数量缓存到向量库或 Redis 当真相

## 高风险写操作

创建订单、调整库存、退款等未来应：

1. 预览将要发生的变更
2. 用户确认
3. 再调 ERP Action API

查询类 Tool 可以直接调用。V15 不实现审批 UI。
