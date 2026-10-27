# Copilot 企业智能工作台导航

## 信息架构

Copilot 使用“全局模块导航 + 当前模块局部导航”，不再把实现层的 Proposal、Approval、Execution、Workflow 和 Evaluation 全部暴露为一级菜单。

| 分组 | 入口 | 路由 | 可见条件 |
| --- | --- | --- | --- |
| 智能工作空间 | ERP 智能助手 | `/chat` | `copilot:use` |
| 智能工作空间 | 业务洞察 | `/insights` | `copilot:insight:read` |
| 智能工作空间 | 我的任务 | `/tasks` | `copilot:use` |
| AI 创作 | 广告创作 | `/ads` | 当前为“即将上线”占位页 |
| AI 创作 | 创作历史 | `/creative-history` | 当前为“即将上线”占位页 |
| 管理与开发 | AI 管理中心 | `/manage` | `copilot:evaluation:read` |

菜单隐藏只用于改善体验。Insight 和 Evaluation API 仍分别使用服务端 IAM 权限依赖执行授权与租户校验。

## 局部导航

- ERP 智能助手：侧边栏下半区显示新建对话、搜索和当前租户的会话历史；离开 `/chat` 后不查询或展示会话历史。
- 我的任务：使用 URL 查询参数保存页签状态，支持全部任务、待我处理、业务草稿、审批任务、执行记录和流程进度。
- 业务洞察：业务预警优先，规则、检测运行和通知保留在页内分区，并继续遵循读/管权限。
- AI 管理中心：统一提供 Agent 任务评测、运行追踪说明和安全边界；Knowledge 检索评测仅在用户具有 `knowledge:read` 时显示。

“全部任务”是 Proposal、Execution 和 Workflow 已加载页面结果的只读前端聚合视图，不创建统一任务实体，也不宣称提供跨来源精确分页。审批页继续调用原 Approval API；后端要求 `copilot:approve` 并按租户过滤。

## 路由兼容

旧书签通过前端重定向继续有效：

- `/drafts` → `/tasks?tab=drafts`
- `/approvals` → `/tasks?tab=pending`
- `/workflows` → `/tasks?tab=workflows`
- `/evaluations` → `/manage`
- `/history` → `/creative-history`

工作流详情的新地址是 `/tasks/workflows/:id`。旧 `/workflows/:id` 仍可打开，避免外部深链接失效。

## 微前端与租户安全

Knowledge 评测入口使用 Shell 注册地址 `/knowledge/datasets`，并以顶层导航交给 Shell/Wujie 处理，不硬编码开发端口。Knowledge 应用继续执行自己的 `knowledge:read` 权限检查和租户上下文校验；Copilot 不读取或合并 Knowledge 的评测表。

TanStack Query key 均包含租户 ID。租户切换会中止当前请求、增加工作区 epoch、清除选中会话并重新挂载页面，避免旧租户缓存继续显示。聊天流和页面请求仍沿用现有 AbortController 清理机制。

## 验收建议

除单元测试、类型检查和生产构建外，具备本地四服务环境时还应通过 Shell 验证：窄屏抽屉、侧边栏折叠、浏览器前进/后退、旧深链接、Wujie keep-alive、跨应用 Knowledge 跳转，以及租户切换和退出后的缓存清理。
