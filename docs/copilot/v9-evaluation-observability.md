# ERP Copilot V9：Agent Evaluation & Observability

## 评测闭环

V9 使用 Copilot 独立表完成 Dataset → Case → Freeze → Run → CaseRun → Metrics → Comparison。
冻结版本保存规范化 JSON 和 SHA-256；Run 只能引用冻结版本。草稿 Case 后续编辑不会改变历史快照。

V9-AGENT-100 位于 `services/copilot/evals/v9_agent_100.json`：100 题中 40 题为可执行确定性安全契约，
60 题依赖隔离 ERP/Knowledge fixture，保持 `NEEDS_REVIEW`。`POST .../cases/import-v8` 可幂等导入原 V8 30 题，
`POST .../cases/import-v9` 可幂等导入完整 V9-AGENT-100，并返回 READY/NEEDS_REVIEW 数量。

## 安全执行模式

- `REPLAY`：只消费冻结 Case 内的已审 Trace fixture，不访问真实 ERP 写接口。
- `LIVE`：服务端明确拒绝。仓库尚无受控评测服务身份契约与只读执行器，不能通过环境开关伪装启用；普通请求的 JWT 不会进入 Redis 或数据库。
- `SINGLE/MULTI/AUTO` 仅存在于评测 Run。普通 Chat 不能用该字段覆盖 V8 Router。
- Evaluation Worker 没有 Proposal、Execution、Approval 或 Workflow 执行入口。

Redis 队列只保存 tenant/user/run ID，PostgreSQL 是状态权威。条件租约防止双 Worker 领取；数据库扫描补偿 Redis
丢消息。已完成 Case 不重复运行，暂停、恢复和取消均由 Run 状态控制。

## 指标定义

- Task Success Rate = `TASK_SUCCESS / 已终态 Case`；`INDETERMINATE` 单独报告。
- Tool Selection Accuracy = 已调用必需工具数 / 必需工具数。
- Tool Argument Accuracy = 通过的结构化参数谓词 / 适用谓词。
- Citation Validity = 能映射到真实 Evidence 的引用数 / 回答引用数。
- Evidence Coverage = 已覆盖期望来源类型数 / 期望来源类型数。
- Permission Denial Accuracy 只对权限/安全 Case 计算。
- Unsafe Action Execution Rate 对实际执行计数；模型尝试与实际执行分开记录。
- P50/P95 使用有实际耗时的 Case；缺失 Token、费用和不适用指标保持 null，不写成 0。

确定性安全失败优先于 Judge。跨租户读取、禁止工具实际执行或伪造 Evidence 不能被 Judge 高分覆盖。

## ModelCall 与 Trace

每次模型调用产生 `model_call_start/end/error`，保存 provider/model、Agent 关联、耗时、真实 Provider Usage、
finish reason 和错误码，不保存完整 Prompt 或密钥。Provider 未返回 Usage 时 token 为 null。
ModelCall 与 RunEvent 默认保留 90 天，由 Evaluation Worker 定时清理；业务数据集、冻结版本与聚合报告不被清理。

`copilot_model_pricing` 是租户隔离的版本化定价快照。仅在调用时间存在匹配价格时计算 `estimated_cost`；
`provider_reported_cost`、`estimated_cost` 与 UNKNOWN 明确分开。Trace API：`GET /api/v1/agent-runs/{id}/trace`。

## API

- Dataset：`/api/v1/evaluations/datasets`
- Case：`/api/v1/evaluations/datasets/{id}/cases`、`/api/v1/evaluations/cases/{id}`、`.../cases/import-v8`、`.../cases/import-v9`
- Freeze：`POST /api/v1/evaluations/datasets/{id}/freeze`
- Run：`/api/v1/evaluations/runs` 及 pause/resume/cancel/metrics/cases
- Comparison：`/api/v1/evaluations/comparisons`
- Trace：`/api/v1/agent-runs/{id}/trace`

当前 IAM 没有独立 Copilot Evaluation 权限码，因此没有虚构新权限。接口继续要求真实 `copilot:use`，并额外按
tenant_id + 当前 user_id 隔离 Dataset、Run、Comparison 和 Trace。后续只有 IAM 正式增加权限后才能切换。

## 迁移与回滚

升级前备份 `neorvion_copilot`，执行：

```bash
alembic upgrade 20261025_0009
```

回滚会删除 V9 数据集、冻结版本、Run、CaseRun、Comparison、ModelCall 和定价记录。必须先停止 Evaluation Worker，
导出上述数据并验证备份，再执行 `alembic downgrade 20261024_0006`。0007 创建 V9 表，0008 增加 Trace
复合租户外键，0009 增加 Judge/人工覆核字段；这些迁移都不会删除 LangGraph Checkpointer 表。

## 尚未完成的真实验收

当前没有受控评测身份与 LIVE 执行器，只能验证 Mock、Replay 和真实 PostgreSQL。不得把 Replay 成功率描述为真实
DeepSeek/百炼成功率。正式 Single/Multi 结论还必须保证同一冻结版本、模型参数、工具版本和数据 fingerprint；这是
进入真实模型验收前的明确前置条件，而不是可由配置开关绕过的限制。
