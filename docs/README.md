# Neorvion 文档导航

当前有效状态：`docs/current-state.md`。新 Agent 会话还要读仓库根目录 `AI_CONTEXT.md`。

## 架构与开发

- [IAM 统一认证与权限架构学习手册](architecture/iam-authentication-authorization-guide.md)
- [架构](architecture.md)
- [核心 ER](er.md)
- [项目目录](project-structure.md)
- [开发规范](development-rules.md)
- [日常开发命令](development.md)
- [API 约定](api.md)
- [数据库](database.md)
- [幂等](idempotency.md)
- [性能与索引](performance.md)
- [业务编号](numbering.md)

## 业务域

- [多租户](multi-tenancy.md) / [RBAC](rbac.md) / [认证](auth.md)
- [商品](products.md) / [仓库](warehouses.md) / [库存](inventory.md)
- [采购](purchases.md) / [履约（收货/出库）](fulfillment.md)
- [销售订单](orders.md) / [物流](shipping.md)
- [盘点](stocktake.md) / [调拨](stock-transfer.md)
- [销售售后](after-sales.md) / [退货单](returns.md) / [采购退货](purchase-returns.md)
- [报表](analytics.md) / [事件](events.md) / [操作日志](operation-logs.md) / [异步任务](async-tasks.md)

## 基础设施

- [生产部署（腾讯云 / 第一次上线）](deployment-production.md)
- [生产运维与排障](server-operations.md)
- [GitHub CI/CD](github-cicd.md)
- [本地 Docker 部署](deployment.md)
- [备份](backup.md)
- [微前端接入](micro-frontend-integration.md)
- [AI 知识库 Knowledge V5](knowledge.md)
- [RAG 评测 100 题](knowledge/evaluation/README.md)

## 面试与 Agent

- [面试入口](interview/README.md)
- [Agent 接入准备](agent-readiness.md)

## 版本文档

历史里程碑只作当时范围参考。冲突时以代码和 `current-state.md` 为准。

最新收口：[V15](versions/v15.md)。部署里程碑：[V16](versions/v16.md)。
