# Copilot V13 生产准备与集成加固

## 当前结论

V13 已完成第一批 P0 代码加固，但当前环境 Docker/PostgreSQL/Redis 不可用，因此整体状态是 **NOT VERIFIED / 不可发布**。禁止仅凭单元测试把远程 MCP、金额预算或数据库迁移标记为生产通过。

| 发布门禁 | 当前状态 | 证据/缺口 |
| --- | --- | --- |
| ERP Resource Authorization | CODE VERIFIED | 纯函数越权测试通过；待 IAM→ERP 真实 HTTP 验收 |
| Monetary Budget Gate | NOT VERIFIED | Lua 和 Mock Redis 测试通过；待真实 Redis 100 并发及重启对账 |
| MCP SDK Compatibility | PROTOCOL TESTED | 官方 SDK 内存传输 tools/list + tools/call 通过；待真实 HTTP |
| MCP Egress | NOT VERIFIED | 生产必须独立 Proxy/ACL；远程开关保持 false |
| Database Migration | NOT VERIFIED | Alembic 唯一 head 为 `20261029_0013`；未对真实 PostgreSQL 执行 |
| LIVE Evaluation | NOT VERIFIED | 未开放 |
| Browser / Nginx / Workers | NOT VERIFIED | 未运行真实 E2E |

## 金额预算契约

- 币种由 `TenantAIQuota.currency` 指定，Redis 和审计表按百万分之一的整数存储，不使用浮点累加。
- 只接受当前 Provider/Model、币种一致、`effective_from` 已生效的版本化价格。
- 聊天按 `BUDGET_MAX_MODEL_CALLS_PER_REQUEST` 和输入/输出价格的较大值预留。在多 Agent Usage 可信聚合完成前，聊天按预留上限结算；Insight 单次调用可按 Provider Usage 结算。
- 缺失 Usage、超时和不确定结果不释放成 0。Redis 不可用时失败关闭。
- `copilot_ai_budget_reservations` 保存 PENDING/ACTIVE/SETTLED/REJECTED/FAILED 审计；Redis reservation hash 保证同一预留不重复结算。

V10 历史迁移使用了当前 ORM metadata，会使 V11 的 `attempt_count` 在空库回放时被提前创建。V11 已改为 `ADD COLUMN IF NOT EXISTS`，避免新库升级重复列；该修复已通过 offline SQL 生成，仍需在备份后的真实 PostgreSQL 上做 upgrade/downgrade 演练。

## 环境验收命令

```bash
docker compose up -d postgres redis iam-api erp-api knowledge-api copilot-api
uv run --directory services/copilot alembic current
uv run --directory services/copilot alembic upgrade head
uv run --directory services/copilot alembic downgrade 20261028_0012
uv run --directory services/copilot alembic upgrade head
uv run --directory services/copilot pytest tests/test_postgres_integration.py
```

downgrade 会删除 V13 预算审计表，只能在隔离测试库或完成备份后执行。真实 Redis 验收需要 100 个并发预留，校验 `used + reserved <= monthly_budget`、重复结算只扣一次、进程中断后可对账，再将结果作为发布证据。

## 回滚

1. 保持 `MCP_REMOTE_EXECUTION_ENABLED=false` 并停止新模型流量。
2. 备份 `copilot_ai_budget_reservations`、当月 Redis quota key 和 Copilot 业务库。
3. 回滚应用到 V12 代码；只在确认不再需要 V13 审计数据时由发布负责人执行 downgrade。
4. 任何超额或对账不一致都保持失败关闭，不得通过改为软限额恢复流量。
