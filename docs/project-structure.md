# 项目目录

只描述关键职责。不要把 `node_modules`、`.venv`、构建产物当架构。

```text
neorvion-erp/
├── AI_CONTEXT.md              # 新会话开发规则
├── apps/
│   ├── shell/                 # 宿主：登录、租户、Wujie
│   ├── erp/                   # ERP 子应用：业务页
│   └── knowledge/             # Knowledge 子应用：知识库
├── packages/shared/           # Query Key、ApiError、租户头规则
├── services/
│   ├── erp/                   # ERP FastAPI + MySQL
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── core/
│   │   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   ├── repositories/
│   │   │   ├── services/
│   │   │   ├── scripts/
│   │   │   ├── agents/        # 预留
│   │   │   └── tasks/
│   │   ├── alembic/
│   │   └── tests/
│   ├── knowledge/             # Knowledge FastAPI + PostgreSQL
│   ├── copilot/               # FastAPI + LangGraph；V1-B 模型对话
│   └── customer-service/      # 未来，尚未创建
├── docs/
├── nginx/
└── docker-compose.yml
```

## 新代码放哪

| 类型 | 位置 |
| --- | --- |
| 新 HTTP 接口 | `services/erp/app/api/v1/`，挂到 `router.py` |
| 新业务规则 | `services/erp/app/services/` |
| 新表 | `models/` + 新 Alembic revision，不改已执行的旧 migration |
| 新页面 | `apps/erp/src/pages/`，路由 `apps/erp/src/router/routes.ts` |
| 共享类型 / Query Key | `packages/shared` |
| 认证 UI | `apps/shell`，不要在 ERP 再做登录 |
| Knowledge API | `services/knowledge/`，独立 FastAPI + PostgreSQL，禁止注册到 ERP |
| Knowledge 页面 | `apps/knowledge/`，由 Shell `/knowledge` 挂载 |

ERP 业务菜单不要放进 `packages/shared`。
