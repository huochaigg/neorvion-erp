# ERP Copilot V7 工作流

## 模型配置

正式运行使用 `openai_compat`，不允许生产环境使用 Mock。密钥仅通过 `CHAT_API_KEY`、`DEEPSEEK_API_KEY` 或
`DASHSCOPE_API_KEY` 注入。启动后先访问 `/api/v1/model-status`；只有 `available` 表示模型端点探测成功。
模型调用失败会返回明确错误，不会生成 Mock 文案。

## 权威边界

Workflow Graph 只编排，PostgreSQL Workflow 表保存业务状态；V5 Proposal 保存可编辑草稿，V6 Execution 与 ERP
Receipt 保存确认、审批和最终写入结果。Redis 只唤醒 Worker。Graph State 和 Workflow 表都不保存 JWT、API Key
或 HMAC Secret。恢复请求必须重新通过 IAM 当前快照。UNKNOWN 自动对账只读 ERP Receipt，使用短期 HMAC、原
tenant 和原 execution key；该内部接口不接受业务 payload，也不能触发 ERP 写入。Worker 会从 PostgreSQL 扫描
过期租约以弥补 Redis 消息丢失；对账按有限次数指数退避，耗尽预算后转人工介入，不会把 UNKNOWN 直接改为失败。

## 发布顺序

1. 备份 `neorvion_copilot`，执行 `alembic upgrade head` 到 `20261024_0005`。
2. 注入真实模型 Secret，并确认 `/model-status` 为 `available`。
3. 启动 Copilot API 和独立 `copilot-worker`。
4. 使用专用测试租户完成 Chat、Tool、Knowledge、Proposal、V6 Execution 和 Workflow 浏览器验收。
5. 监控 PAUSED、RECONCILING、NEEDS_MANUAL_INTERVENTION、步骤耗时和重试次数。

数据库降级会删除 Workflow 状态、事件和尝试记录。生产回滚应先停止创建和恢复请求、导出工作流审计、处理全部
RUNNING/RECONCILING，再回退应用；通常保留 V7 表比立即 downgrade 更安全。

## 补偿

只读、分析和未执行 Proposal 可以安全停止或重试。ERP 单据创建没有通用逆操作；采购、销售和调拨创建成功后，
V7 不删除、不强制取消、不创建反向调拨，而是停止后续调度并进入人工介入。
