# V11 Enterprise AI Governance

## 身份与信任边界

IAM 是服务身份唯一权威。`SERVICE` Token 最长五分钟，绑定 `service_id`、目标 Audience、
tenant scope、只读 scope、资源白名单和 credential version。IAM 每次内部授权都会查询 MySQL，
因此吊销、轮换、租户停用和授权收缩不会等待 JWT 自然过期。ERP/Knowledge 对服务身份回源
IAM；用户专属及高风险写接口拒绝 SERVICE。`DELEGATED` Claim 已能被共享校验器识别，但签发与
授权流程未开放。

ERP 当前已支持服务身份的租户、Audience 和只读 Scope 复核，但各业务只读端点尚未完成统一的
资源参数绑定契约。带资源 Claim 的 Token 在未声明本次资源时由 IAM 拒绝。因此 V9 LIVE 继续硬
关闭，资源受限的周期规则也应保持禁用；不得以移除资源约束作为生产绕过方案。

明文 Secret 只在创建或轮换响应出现一次，IAM 仅保存 Argon2 哈希。不要让 Insight、Evaluation
和 Workflow Worker 共用身份。不得把服务 Token 放入 Redis、数据库、日志或前端。

权限目录同步和角色授权是两件事。本版本不会自动把新增权限授给现有角色。批量授权前必须另行
核对目标租户、角色、成员数、提权影响和回滚 SQL，并取得批准。

## 数据库迁移与回滚

升级前分别备份 IAM MySQL 和 `neorvion_copilot` PostgreSQL，再执行：

```bash
uv run --directory services/iam alembic upgrade head
uv run --directory services/copilot alembic upgrade head
```

IAM 迁移创建 `service_identities` 与 `service_identity_audits`。Copilot 迁移
`20261027_0011` 创建 Provider、Model、Policy、Quota、Governance Audit、Retention Run 表，
并给 Insight Run 增加 `attempt_count`。回滚前先停止 Scheduler/Worker 和治理写流量并导出新增表；
downgrade 会删除 V11 表，不能在未备份时执行。

## Scheduler、配额与模型

Scheduler 以 `rule + schedule window` 幂等建任务；PostgreSQL 是状态权威，Redis 只传 ID。Worker
用服务凭据换取 ERP Audience 短 Token，领取、续租、有限重试并通过数据库补偿扫描恢复 Redis
丢消息。默认关闭，服务身份未配置时拒绝启动。

Chat 与 Insight 分析先通过 Redis Lua 原子预留 RPM、日请求、月 Token 和并发额度，完成后按
Provider Usage 结算；缺失 Usage 保持 UNKNOWN。生产关闭配额会拒绝启动。Provider Secret 只从
登记的环境变量读取，必须真实探测成功后才能启用。

## 数据保留与验证

V11 API 只提供 Conversation、AgentRun 和 ModelCall 的租户级 Dry Run，不删除 Receipt、UNKNOWN
对账或业务审计。物理清理仍需备份和独立审批。

```bash
uv run --directory services/copilot ruff check app tests
uv run --directory services/copilot pytest -q
corepack pnpm --filter @neorvion/copilot lint
corepack pnpm --filter @neorvion/copilot test
corepack pnpm --filter @neorvion/copilot build
docker compose config
```

真实验收必须另外覆盖 IAM MySQL、Copilot PostgreSQL、Redis、ERP/Knowledge HTTP、真实模型和
浏览器。Mock/静态测试不能替代这些结果。
