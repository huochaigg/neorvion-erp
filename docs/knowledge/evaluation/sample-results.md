# V5 抽样评测结果

本次 **没有写入硬编码指标**。下列 3 题尚未在租户 3 上跑通真实 probe。

预定抽样：

| 编号 | 意图 | 状态 |
| --- | --- | --- |
| erp-002 | ERP 确认订单只预占、不扣 `quantity` | 未执行 |
| ecom-008 | 模拟跨境头程/尾程 | 未执行 |
| adv-006 | 无答案：真实平台佣金百分比 | 未执行 |

## 阻塞项（不得假装成功）

1. **登录密码未注入当前执行环境。** 脚本只读取 `KNOWLEDGE_SEED_PASSWORD`，没有该变量时直接退出码 2，不会绕过 JWT。本机 Shell 已有登录会话，但初始化脚本不能使用浏览器内存中的 Access Token（禁止把 JWT 写入日志或对话）。
2. **`services/knowledge/.env` 未配置 `EMBEDDING_API_KEY` / `CHAT_API_KEY`。** 即使补上密码完成上传与切片，VECTOR / HYBRID 向量路与模型生成也会因「未配置 Embedding/Chat API Key」失败。KEYWORD 仍可用（simple FTS + trigram，不是 BM25）。
3. **未配置 Rerank 模型。** `rerank=true` 时会 `rerank_degraded=true`，结果退回融合序。

已确认可用、与评测无关的基础设施：

- Knowledge `GET /api/v1/health`：`postgres=ok`，`pgvector=ok`，`identity=ok`，`milestone=Knowledge V5`
- ERP `GET /api/v1/health`：`mysql=ok`，`redis=ok`
- 本地 Knowledge DB 已 `alembic upgrade` 至 `20261014_0006`
- 本地 `TASK_EXECUTOR=inline`，上传请求内即可 PARSE/CHUNK，不必另开 Worker
- 前端已打开：`/knowledge/datasets`（评测数据集）、`/knowledge/recycle`（回收站）、`/knowledge/api-keys`（API Key）

## 你需要做的

```powershell
$env:KNOWLEDGE_SEED_PASSWORD = "<本地密码，不要提交>"
# 若要跑模型生成（会计费），先在 services/knowledge/.env 填写 Embedding/Chat Key，再：
# $env:KNOWLEDGE_SEED_GENERATE = "1"
cd services/knowledge
uv run python -m app.scripts.seed_eval_v5
```

脚本成功后会用真实 `probe` 覆盖本文件。只自动跑上述 3 题，其余 97 题请在页面「单题评测」或「检索评测」里自己选策略运行。
