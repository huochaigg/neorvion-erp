# 开发规范

## Git

禁止 Agent 自动 add / commit / push / tag / reset / rebase。禁止自动创建 / push `production` 分支。禁止自动 SSH 腾讯云。保持未提交，需要时只建议 Commit Message。

## Python / SQLAlchemy

- SQLAlchemy 2 风格。Model 业务含义不直观的列可写 comment；不要为统一注释大规模 migration
- Schema / Swagger 中文 description 优先
- 复杂方法：中文 docstring + 关键步骤注释。CRUD 不要堆废话
- 金额核心路径用 Decimal / Numeric，不要用 float 做财务计算
- 业务异常走 `AppError` + 稳定 `code`（如 `INSUFFICIENT_AVAILABLE_INVENTORY`），不要随机数字

## 事务

Repository 不 commit。Service 在 Action 成功路径 commit。库存、单据、流水、事件同一事务。多 SKU 按 `sku_id` 升序加锁。

## API

- 资源复数 + action：`/sales-orders/{id}/confirm`
- 列表：`page` / `page_size` / `total` / `items`，`page_size <= 100`
- 默认 `created_at DESC`；流水 / 日志 `occurred_at DESC`
- 排序字段必须白名单
- PATCH 用 `model_fields_set` 区分未提交和显式 null
- 跨租户 404

## React

- 租户数据 Query Key 含 `tenantId`
- 服务端数据不要再塞 Zustand
- Mutation 精准 invalidate，禁止 `queryClient.clear()`
- 权限：菜单隐藏 + `PermissionGuard` + 后端 `require_permission`
- Table 保持 V6.1：`#root` 100%、Flex、`min-height: 0`、表体内滚动
- 不留 `debugger`；生产不要无意义 `console.log`

## 测试

`backend/tests/` 按领域文件组织。高频 setup 放 `tests/helpers/factory.py`。不要为 Factory 重写全部旧测试。并发测试覆盖预占竞争、双 confirm、售后可退、调拨、任务 retry。

## 文档

有效状态写 `current-state.md`。版本历史不要复制进当前状态。演示数据必须标明 synthetic。不要伪造生产指标。

## AI / Cursor

先读 `AI_CONTEXT.md`。不要开始 Agent 项目，除非用户明确要求。
