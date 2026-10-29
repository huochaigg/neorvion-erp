# V12 MCP + Agent Skills 受控工具生态

## 范围与默认状态

V12 只接入租户级、只读、人工审核的 Streamable HTTP MCP 工具，并增加声明式 Agent Skill。远程 MCP 默认关闭；stdio、任意 URL、动态代码、SQL/Shell、ERP 写入、自动审批和自动执行不在本版本范围。V9 LIVE Evaluation 仍保持原门禁状态。

实现使用 MCP Streamable HTTP 的 JSON-RPC `initialize`、`tools/list`、`tools/call` 子集。仓库当前没有锁定可验证的 Python MCP SDK，因此没有引入无约束新依赖；升级 SDK 前必须做协议兼容测试和依赖审计。

## 权限与审批

新增 `copilot:mcp:read/manage` 和 `copilot:skill:read/manage`，但不自动授予任何角色。Server、每个工具 Schema 版本、每个 Skill 版本均独立审核。Server 配置改变会自动停用并重新待审；Schema Hash 变化会保留旧版本、将其停用并创建新待审版本。模型只看到租户、Server、Tool、IAM、治理策略和 Agent 白名单的交集。

## 网络与 Secret

```env
MCP_REMOTE_EXECUTION_ENABLED=false
MCP_ALLOWED_HOSTS=mcp.vendor.example
MCP_EGRESS_PROXY_URL=http://controlled-egress-proxy:3128
MCP_NETWORK_ISOLATION_ACKNOWLEDGED=false
MCP_BUDGET_GATE_VERIFIED=false
```

Endpoint 必须为白名单内 HTTPS 域名，禁止内嵌凭据、query、fragment、重定向和私网/回环/保留地址。调用前重新解析全部 DNS 结果。应用层复核不能消除解析与连接间竞态，因此生产强制要求受控 Egress Proxy/网络策略执行 IP 固定和出站 ACL。V11 金额预算并发硬限制尚未验收，`MCP_BUDGET_GATE_VERIFIED` 默认 false；目标环境完成硬门禁验证前，生产启动检查会拒绝开启远程 MCP。

Bearer 只登记环境变量名，密钥不入数据库、不返回 API、不写审计。响应受大小、时间、并发和脱敏限制；Redis 并发门禁不可用时失败关闭。

## 工具和 Skill 边界

- MCP 参数只接受受限 JSON Schema object 子集，拒绝动态引用、组合 Schema 和 tenant/token/URL/code/SQL/shell 控制参数。
- 执行前重新查库并复核权限、Agent、资源范围和版本；出网前结束数据库事务。
- 返回值标记为不可信，Evidence 来源为 `MCP`，不能覆盖系统规则。
- Skill 是不可执行文本、Schema 和依赖清单，不是 Python 插件。输出必须通过 Schema；要求 Evidence 时无证据即失败。
- `services/copilot/skills/*.json` 提供库存分析、销售订单审查、授权知识研究模板；通过 API 导入后仍需人工审核。

## 初始化、验证与回滚

```bash
uv run --directory services/copilot alembic upgrade head
uv run --directory services/copilot pytest -q tests/test_v12_ecosystem.py
pnpm --filter @neorvion/copilot build
```

迁移创建五张 V12 表，并扩展 Evidence 来源约束。回滚前先关闭远程执行、停用 Server、备份数据库，再执行 Alembic downgrade。关闭 `MCP_REMOTE_EXECUTION_ENABLED` 可立即切断远程 MCP 而不删除治理记录。

生产还必须验证 Egress ACL、DNS rebinding、重定向、超时/大响应、Redis 故障关闭、Schema 变更重审、跨租户、SSE 断开和审计脱敏。Mock/单元测试不能替代真实联调。
