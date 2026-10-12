# 架构

为什么是模块化单体：当前团队与数据量不需要微服务。拆服务会把库存事务拆穿。Shell + ERP 微前端只解决部署和权限入口，后端仍是一个 FastAPI。

为什么 Repository 不 commit：HTTP 一次 Action 常改多表。提交权在 Service，才能和库存、流水、Outbox 同事务。

为什么不用 GraphQL / Kafka / K8s：Core V1 目标是正确的库存与状态机，不是平台工程展示。
