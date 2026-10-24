# ERP Copilot V8 Multi-Agent

## 安全边界

V8 同时保留 Single Agent 与 Multi-Agent。确定性 Router 仅将跨领域复杂分析交给 Supervisor；简单查询继续走
V1–V7 单 Agent。专业 Agent 仅查询、检索和建议，正式业务动作仍必须经过 V5 Proposal、V6 Execution 或 V7
Workflow。

Agent Registry 固定注册 Sales、Inventory、Procurement、Knowledge 和 Supervisor。工具权限是当前 IAM 权限、Agent
白名单、Tool 权限和下游资源授权的交集。Supervisor 没有工具；子 Agent 不接收完整会话、JWT、HMAC Secret 或
其他 Agent 的自然语言历史，只接收裁剪后的 TaskInput 和结构化 AgentResult。

## 路由、Graph 与 Trace

`MultiAgentGraph` 使用 StateGraph 和 Send。简单请求进入原 `CopilotWorkflow`；跨领域请求并行运行无依赖专业
Agent，Procurement 在销售/库存结果之后运行，最后由无工具 Supervisor 汇总。并发数、Agent 数、单 Agent 工具
数、上下文、结果大小和总时限均由服务端配置限制。

迁移 `20261024_0006` 新增 `copilot_agent_runs`、`copilot_agent_task_runs`，并为 ToolRun/Evidence 增加 Agent 关联。
SSE 新增 `agent_route`、`agent_start`、`agent_progress`、`agent_end`、`agent_error`。Trace 不保存完整 Prompt、JWT
或 Secret；模型未返回 usage 时保持 null。

## 迁移、回滚与评测

发布前备份 `neorvion_copilot`，执行 `alembic upgrade head`。回滚前停止新 Chat 流量并导出 Agent Trace，然后执行
`alembic downgrade 20261024_0005`。回滚只删除 V8 Trace 与 Agent 关联列。

`services/copilot/evals/v8_cases.json` 提供 30 个确定性路由和安全基线 Case。真实 Single/Multi 质量、延迟、Token、
费用对比必须在同一测试租户、数据快照、模型和预算下运行；没有可靠 usage 时不得生成伪造成本结论。
