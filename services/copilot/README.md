# Neorvion ERP Copilot V2

独立 FastAPI + LangGraph 服务，默认端口 `8013`。V2 在 V1-B 对话能力上增加受控的 ERP 只读 Tool Calling，不连接 ERP 数据库、不导入 ERP 内部模块、不执行写操作，也不持久化会话。

## API 与事件

| API | 说明 |
| --- | --- |
| `GET /api/v1/health` | 公开健康检查 |
| `GET /api/v1/me` | 已验证的租户上下文和权限 |
| `POST /api/v1/chat` | 多轮工具循环后的完整回答 |
| `POST /api/v1/chat/stream` | SSE：`message`、`tool_start`、`tool_end`、`tool_error`、`done`、`error` |

客户端只能发送有限的 `user` / `assistant` 上下文，最后一条必须是 `user`。工具名、参数 Schema、租户、权限与下游地址均由服务端决定。

当前白名单工具：

- `get_sales_order`、`list_sales_orders`
- `get_inventory`
- `get_product`、`search_products`
- `list_purchase_orders`
- `get_warehouse`
- `get_after_sale`

没有注册 `list_low_stock_skus`：现有 ERP 库存 API 的 `threshold` 是调用方临时查询参数，不是可信、持久化的 SKU 安全库存配置。V2 只返回客观库存数量，不把临时阈值包装成补货结论。

## 身份与安全边界

IAM 当前 Access Token 同时包含 `neorvion-copilot` 和 `neorvion-erp` audience。Copilot 先校验 JWT、租户快照与 `copilot:use`，工具执行时再检查 ERP audience，然后只把原始用户 Token 与已验证的 `X-Tenant-ID` 转发到 ERP。ERP 会独立验证 JWT、租户成员关系和具体 `*:read` 权限。

工具调用还会执行：服务端白名单、Pydantic `extra=forbid` 参数校验、最大轮次/调用数/总时限、结果字段白名单、大小截断。ERP 结果用不可信数据边界包裹后才交给模型；Token、租户参数、客户电话/地址、仓库联系方式不会进入模型上下文。

## 配置

```env
MODEL_PROVIDER=openai_compat
CHAT_BASE_URL=https://api.deepseek.com
CHAT_API_KEY=
CHAT_MODEL=deepseek-chat
CHAT_TIMEOUT_SECONDS=30
CHAT_MAX_OUTPUT_TOKENS=1024

ERP_BASE_URL=http://127.0.0.1:8011
ERP_JWT_AUDIENCE=neorvion-erp
ERP_CONNECT_TIMEOUT_SECONDS=3
ERP_READ_TIMEOUT_SECONDS=10
TOOL_MAX_ROUNDS=5
TOOL_MAX_CALLS=8
TOOL_TOTAL_TIMEOUT_SECONDS=30
TOOL_MAX_RESULT_CHARS=12000
TOOL_MAX_PAGE_SIZE=50
```

百炼可使用 `CHAT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` 和兼容 Tool Calling 的模型。密钥只能放本地 `.env` 或部署 Secret。

## 本地运行与测试

```bash
uv sync --directory services/copilot
uv run --directory services/copilot python -m app
uv run --directory services/copilot ruff check app tests
uv run --directory services/copilot pytest -q --tb=short
```

测试使用 mock 模型与 `httpx.MockTransport`，不调用真实 IAM、ERP 或付费模型。

## 调用示例

```bash
curl -X POST http://localhost:8013/api/v1/chat \
  -H "Authorization: Bearer <multi-audience-access-token>" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"查询 SKU-001 的可用库存"}]}'
```

```bash
curl -N -X POST http://localhost:8013/api/v1/chat/stream \
  -H "Authorization: Bearer <multi-audience-access-token>" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"订单 123 当前状态是什么？"}]}'
```

## V2 明确不做

前端、会话数据库、RAG/Knowledge、任意 URL/SQL/Shell 工具、多 Agent、Checkpointer、写操作、审批和自动补货均不在本版本范围内。
