# Neorvion ERP Copilot V1-B

独立 FastAPI + LangGraph 服务，默认端口 `8013`。V1-B 只提供受 IAM 鉴权保护的模型对话，不连接 ERP MySQL，不包含 ERP/Knowledge Tool，不执行任何业务写操作，也不持久化会话。

## 当前 API

| API | 说明 |
| --- | --- |
| `GET /api/v1/health` | 公开健康检查，不返回配置或密钥 |
| `GET /api/v1/me` | 已校验租户上下文和 `copilot:use` 权限 |
| `POST /api/v1/chat` | 单次非流式对话 |
| `POST /api/v1/chat/stream` | SSE 流式对话，事件为 `message` / `done` / `error` |

聊天请求只能传 `user` / `assistant` 消息，最后一条必须是 `user`。系统提示只在服务端注入。V1-B 不创建会话表；调用方需要在每次请求中携带有限历史。

## 模型配置

复制 `.env.example` 为 `.env`。真实密钥不得提交 Git。

```env
MODEL_PROVIDER=openai_compat
CHAT_BASE_URL=https://api.deepseek.com
CHAT_API_KEY=
CHAT_MODEL=deepseek-chat
CHAT_TIMEOUT_SECONDS=30
CHAT_MAX_OUTPUT_TOKENS=1024
```

百炼 OpenAI-compatible 接口示例：

```env
MODEL_PROVIDER=openai_compat
CHAT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_API_KEY=
CHAT_MODEL=qwen-plus
```

`CHAT_API_KEY` 为空时依次回退 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`。`MODEL_PROVIDER=mock` 只用于测试或本地界面联调。

模型超时、429 与 5xx 会转换为稳定业务错误。V1-B 的交互式请求不自动重试，避免供应商已经接收请求后重复计费；客户端可根据错误提示显式重试。

## 本地运行

```bash
uv sync --directory services/copilot
uv run --directory services/copilot python -m app
```

IAM 必须签发包含 `neorvion-copilot` audience 的 Access Token，并在 Redis 中存在对应用户与租户的授权快照。请求还需要 `copilot:use` 权限。

## API 示例

```bash
curl -X POST http://localhost:8013/api/v1/chat \
  -H "Authorization: Bearer <access-token>" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"你能做什么？"}]}'
```

```bash
curl -N -X POST http://localhost:8013/api/v1/chat/stream \
  -H "Authorization: Bearer <access-token>" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"介绍当前能力"}]}'
```

## 测试

```bash
uv run --directory services/copilot ruff check app tests
uv run --directory services/copilot pytest -q --tb=short
```

测试使用 mock Adapter 和 `httpx.MockTransport`，不会调用真实 IAM、Redis 或付费模型。

## 明确不做

- 不读取或修改 ERP 业务数据。
- 不连接 ERP/Knowledge 内部数据库或 import 它们的内部代码。
- 不支持客户端 system 消息、任意 Tool、多 Agent、Checkpointer 或会话持久化。
- 不把 Prompt 当作权限边界；JWT、租户快照和 `copilot:use` 均由服务端校验。

