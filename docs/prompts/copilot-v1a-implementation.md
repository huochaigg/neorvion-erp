# ChatGPT 代码生成提示词：ERP Copilot V1-A

你是一名资深 Python/FastAPI 平台工程师。请在现有 Neorvion ERP monorepo 中实现 **Copilot V1-A：独立后端骨架、IAM 鉴权、健康检查与测试**。这是第一块可运行切片，不要提前实现聊天、数据库、LangGraph、前端或写操作。

## 仓库现状

```text
neorvion-erp/
├── apps/shell                 # React 19 + Vite + Wujie 宿主
├── apps/erp                   # ERP 微前端
├── apps/knowledge             # Knowledge 微前端
├── services/iam              # FastAPI, :8010, IAM 权威
├── services/erp              # FastAPI, :8011, MySQL 业务服务
├── services/knowledge        # FastAPI, :8012, PostgreSQL/RAG
├── packages/python/neorvion_security
├── packages/python/neorvion_db
└── packages/shared
```

后端统一使用 Python 3.12、FastAPI、Pydantic Settings、pytest、ruff、uv。`services/knowledge` 是最接近的独立服务参考，但 Copilot 不能 import Knowledge 或 ERP 的内部代码。

## 不可违反的架构边界

1. 新服务必须位于 `services/copilot`，默认端口 `8013`，应用名 `Neorvion Copilot`，版本 `1.0.0`。
2. Copilot 不得连接 ERP MySQL，不得 import `services/erp` 或 `services/knowledge` 内部模块。
3. 身份、租户和权限来自 IAM。JWT：issuer=`neorvion-iam`、audience=`neorvion-copilot`。
4. `X-Tenant-ID` 只是意愿，必须使用现有 `neorvion_security` 包和 IAM Redis 授权快照校验；沿用 Knowledge 的依赖注入模式，不复制一套不兼容的 JWT 实现。
5. V1-A 只实现鉴权后的 `/api/v1/me` 和公开 `/api/v1/health`。不实现任何业务 Tool 或写接口。
6. 不添加 LangGraph。V1-A 不需要 PostgreSQL、Alembic 或 Redis 任务队列；IAM 授权快照所需 Redis 配置除外。
7. 不修改旧 migration，不执行 git commit，不写入真实密钥。
8. API 响应、异常结构、request id 和日志风格应与 `services/knowledge` 一致，能复用 `neorvion_security` 时必须复用。
9. 生产环境缺少 JWKS 配置时拒绝启动；开发和测试允许注入假身份依赖。
10. 跨租户和未授权结果不得泄露资源存在性。虽然 V1-A 没有资源接口，测试仍需覆盖租户头缺失/非法、无 bearer token 和 audience 不匹配的入口行为。

## 本切片必须交付

### A. `services/copilot` 工程

- `pyproject.toml`，包含运行依赖、dev 依赖、uv 本地 editable sources、ruff/pytest/pyright 配置。
- `README.md`，说明职责边界、本地启动命令、端口和当前仅有的两个 API。
- `.env.example`，只给安全占位值和本地 URL，不包含真实密钥。
- `Dockerfile`，风格对齐现有 Python 服务；容器只启动应用，不自动跑 migration。
- `app/__init__.py`、`app/__main__.py`、`app/main.py`。
- `app/core/config.py`、`logging.py`、`request_id.py`、`exceptions.py`、`tenant.py`。
- `app/services/identity.py` 或等价封装：复用共享安全包完成 IAM 身份与授权快照读取。
- `app/api/deps.py`、`app/api/v1/router.py`、`health.py`、`me.py`。
- `/api/v1/health` 返回至少 `status`、`service`、`version`、`git_sha`；不得泄露配置与密钥。
- `/api/v1/me` 返回当前 `user_id`、`tenant_id`、权限编码列表与权限版本；字段以现有 `TenantContext` 实际定义为准，不要臆造。

### B. IAM 最小集成

- 将默认 `JWT_AUDIENCES` 增加 `neorvion-copilot`，保持现有 audience 不变。
- 在 IAM 权限常量和权限树中增加最小权限 `copilot:use`，菜单标题“ERP Copilot”。遵循现有权限目录建模与 seed 机制，不新建另一套权限系统。
- 如 IAM 的应用注册 seed 有统一入口，注册 code=`copilot`、name=`ERP Copilot`、audience=`neorvion-copilot`；若当前不存在可靠的应用 seed 入口，则只完成 audience 和权限，README 明确后续步骤，不要随意写数据库初始化旁路。

### C. 根目录集成

- 更新根 `package.json` 不合适，因为 V1-A 只有 Python 服务；不要加入假的 pnpm workspace。
- 更新 `.env.example` 中 Copilot 非敏感配置示例。
- 更新 `docker-compose.yml`：新增 `copilot` 服务，端口 `8013`，依赖 IAM/Redis；IAM 的 `JWT_AUDIENCES` 同步加入 `neorvion-copilot`。不要让 Copilot 连接 MySQL/PostgreSQL。
- 更新 `services/README.md` 与 `docs/project-structure.md`，把 Copilot 从“未来、尚未创建”改为 V1-A 骨架，并写明尚无业务 Tool。

### D. 测试

- `services/copilot/tests/conftest.py` 与 API 测试。
- 健康检查无需 token。
- `/me` 无 token、缺租户头、非法租户、权限不足分别失败；合法上下文成功并返回稳定字段。
- 测试不得访问真实 IAM、Redis 或模型 API，使用依赖覆盖或 fake identity client。
- 若共享安全包已有相同测试 helper，优先按现有模式复用其公开能力，不跨服务 import 测试代码。

## 实现质量要求

- 所有新增代码应通过：

```bash
uv run --directory services/copilot ruff check app tests
uv run --directory services/copilot pytest -q --tb=short
```

- 对修改过的 IAM 代码运行相关测试或至少运行静态检查。
- 类型声明清晰，不使用宽泛 `Any` 掩盖身份字段。
- 中文业务注释只写在不直观处，避免模板化废话。
- 不复制粘贴整套 Knowledge 代码后留下无关的 RAG、数据库或模型配置。

## 工作方式与输出要求

先阅读仓库中的 `AI_CONTEXT.md`、`services/knowledge/app/api/deps.py`、`services/knowledge/app/services/identity.py`、`packages/python/neorvion_security`、IAM 权限目录和现有测试，再实施。

如果你不能访问仓库文件，请不要假装已经修改文件；请基于本提示词输出：

1. 假设与需要核对的字段。
2. 完整文件清单。
3. 可直接应用的 unified diff；不要省略为“其余类似”。
4. 验证命令和预期结果。

如果你能访问仓库，则直接编辑代码、运行验证，并最终汇报修改文件、测试结果和剩余风险。不要执行 git add/commit/push。

