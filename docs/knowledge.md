# Neorvion Knowledge V4

独立 AI 知识库：V1 知识库 CRUD → V2 文档解析与切片 → V3 RAG 检索与智能问答 → V4 RAG 评测与召回调优。身份、租户、RBAC 仍以 ERP MySQL 为权威来源。

## 与 ERP 的关系

```mermaid
flowchart LR
  Browser --> Shell[Shell 8015]
  Shell --> KFE[Knowledge 微前端 8017]
  KFE --> KAPI[Knowledge API 8012]
  KAPI --> ERPAPI[ERP API 8011]
  Worker[Knowledge Worker] --> Redis[(Redis)]
  Worker --> PG[(PostgreSQL + pgvector)]
  KAPI --> PG
  KAPI --> Disk[本地文件目录]
  KAPI --> Models[OpenAI 兼容模型 API]
```

- 登录、Refresh、租户切换仍由 Shell + ERP 负责。
- Knowledge 先验签 JWT，再调用 ERP `POST /api/v1/internal/identity/introspect`。
- 前端传入的 `X-Tenant-ID` 只是意愿，不能单独采信。
- 权限沿用 `knowledge:read/create/update/delete`。检索与问答需要 read；重建索引与模型连通测试需要 update。
- 模型密钥只在 Knowledge 服务端环境变量中，不返回前端，也不写入 Git。

## 信息架构

| 菜单 | 路由 | 说明 |
| --- | --- | --- |
| 工作台 | `/workbench` | 知识库/文档/切片数量、最近文档、待处理任务 |
| 智能搜索 | `/search` | 真实检索引擎：VECTOR / KEYWORD / HYBRID |
| 知识问答 | `/chat`、`/chat/:id` | 会话、SSE 流式回答、引用来源 |
| 知识库 | `/bases` | V1 CRUD |
| 知识库详情 | `/bases/:id` | 概览、文档、切片、向量索引状态与重建 |
| 文档详情 | `/bases/:id/documents/:docId` | 解析预览、切片编辑启停、任务与重试 |
| 召回调优 | `/retrieval-test` | 与问答共用检索引擎；对比 VECTOR/KEYWORD/HYBRID 与 Rerank 前后 |
| 处理任务 | `/tasks` | PARSE / CHUNK / EMBED |
| 模型配置 | `/models` | 平台级 Chat / Embedding / Rerank（无密钥明文） |
| 评测数据集 | `/datasets`、`/datasets/:id` | 数据集 CRUD、导入导出、问题标注 |
| 检索评测 | `/experiments` | 参数方案、异步跑批、单题结果 |
| 实验对比 | `/experiments/compare` | 多 run 指标、参数差异、低分问题 |
| 使用统计 | `/stats` | 来自 retrieval_logs / messages 的真实用量 |

成员与角色仍在 ERP。评测任务落在 PostgreSQL，切页面或切租户不会删除已排队的评测。

切租户后：`/bases/:id` 与文档详情回到工作台，`/chat/:id` 回到 `/chat`，任务详情回到 `/tasks`，`/datasets/:id` 回到 `/datasets`，`/experiments/:id` 回到 `/experiments`。Query Key 带 `tenantId`；页面 `epoch` 会卸掉局部状态并中止进行中的 SSE。前端取消的是浏览器请求，不会取消服务端已落库的解析/索引/评测任务。

## 数据库

迁移：`20261013_0001`（V1）→ `20261013_0002`（V2）→ `20261013_0003`（V3：pgvector + 会话）→ `20261014_0004`（V4 评测）。

V1/V2 表保持不变。V3 增量：

- `document_chunks.search_tsv`：`to_tsvector('simple', content)` 生成列 + GIN；另有 `gin_trgm_ops`。这不是 BM25。
- `chunk_embeddings`：一条切片一行向量。记录 `model_name`、`dimensions`、`content_hash`、`chunk_version`、`PENDING/READY/STALE/FAILED`。检索只使用当前模型、当前维度、`READY`、且 `chunk_version` 与文档 `active_chunk_version` 匹配的行。
- `model_profiles`：平台系统配置镜像（密钥只引用环境变量名）。
- `conversations` / `messages` / `message_citations`：会话、消息、引用来源。
- `retrieval_logs`：检索参数、阶段耗时与排名，供测试页解释。

复合外键始终带 `tenant_id`。索引失败不得破坏 V2 文档与切片。

向量列维度取自迁移时的 `EMBEDDING_DIMENSIONS`（默认 1024）。测试库使用 8 维。**更换维度必须重建迁移或新开库，并全量重建索引。**

## Embedding 与索引

- 供应商：`MODEL_PROVIDER=openai_compat`（兼容 DashScope / Qwen 等 OpenAI 协议）或测试用 `mock`。
- 默认建议：`text-embedding-v3`，维度 1024。查询与文档必须同一模型与维度。
- 批量大小 `EMBEDDING_BATCH_SIZE`（默认 16），后台任务 `TaskType.EMBED`，失败可重试。429 / 5xx 可重试，401 / 402 不盲目重试。
- Chunk 编辑会标记向量 `STALE` 并排队重建；禁用切片不删向量，但检索 SQL 排除 `enabled=false`；删除文档会使进行中 EMBED 失败。
- 当前数据规模走精确余弦 kNN（`cosine_distance`），**不建 HNSW**。小数据 + 多租户 `WHERE` 过滤时 HNSW 容易降低召回。

## 检索引擎

三种策略共用 `RetrievalService.search`，智能搜索 / 检索测试 / 问答不得分叉实现。

| 策略 | 实现 |
| --- | --- |
| VECTOR | Embedding 查询向量 + pgvector 余弦距离，相似度 = `1 - distance` |
| KEYWORD | PostgreSQL `simple` FTS + `pg_trgm` + 中文 `ILIKE`。**不是 BM25** |
| HYBRID | 两路召回后 RRF（`k=60`）融合，按 `chunk_id` 去重 |

可选 Rerank：模型不可用或抛错时降级到融合结果，并标记 `rerank_degraded`。

分数不要混用：向量相似度、关键词分、RRF、Rerank 各自独立，阈值只作用在对应一路。

**租户与授权过滤全部在 SQL `WHERE` 中完成**（`tenant_id`、知识库 ACTIVE、切片 ACTIVE+enabled、当前版本、指定知识库 ID）。禁止先全局召回再在 Python 里丢弃其他租户。

## 知识问答 / SSE

```text
问题 → 检索 → 可选 Rerank → 证据筛选 → 构造上下文 → LLM → SSE
```

- 无命中：明确拒答，不把猜测当知识库事实。
- 文档正文包在 `<untrusted_document>` 中，系统提示要求忽略其中的指令。
- 历史只保留最近 `CHAT_HISTORY_TURNS` 轮，证据字符上限 `CHAT_MAX_CONTEXT_CHARS`。
- LLM 调用期间不持有长事务：先落库用户/助手消息并 commit，再流式生成，最后再写结果与 citation。
- SSE 事件：`status` / `token` / `citation` / `done` / `error`。请求携带 JWT 与已校验的租户头。切租户必须 abort 旧 EventStream。

## 模型配置

平台级 Chat / Embedding / Rerank 来自环境变量。API 只返回 `has_api_key` 与 `api_key_env`，永不返回密钥。普通租户管理员不能覆盖平台密钥。连通测试需要 `knowledge:update`。

本地示例（密钥只写 `services/knowledge/.env`）：

```env
MODEL_PROVIDER=openai_compat
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIMENSIONS=1024
CHAT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL=qwen-plus
```

测试默认 `MODEL_PROVIDER=mock`，不产生计费。

## 解析与切片（V2，仍有效）

| 类型 | 库 | 说明 |
| --- | --- | --- |
| PDF | pypdf | 无文本视为扫描版，明确失败，不做 OCR |
| DOCX | python-docx | 保留 Heading 与段落 |
| Markdown | 文本 + 标题识别 | 保留 ATX 标题 |
| TXT | charset-normalizer | 常见编码 |

切片单位是 **字符**。`FIXED` / `RECURSIVE`。重新切片写入新 `version`，成功后再把旧 `ACTIVE` 标为 `SUPERSEDED`。

## 任务状态机

```text
QUEUED → RUNNING → SUCCESS
                 ↘ FAILED →（重试）QUEUED
```

`PARSE` / `CHUNK` 失败会影响文档状态；`EMBED` 失败不影响 V2 原文与切片。PostgreSQL 是真相；Redis List 只投递 `task_id` 或 `eval:{run_id}`。`TASK_EXECUTOR=inline` 仅建议测试。

Worker：`uv run python -m app.tasks.worker`。评测运行与文档任务共用同一队列，前缀 `eval:` 区分。重启后 RUNNING 评测标失败，QUEUED 重新入队。

## 本地运行

```bash
cd services/knowledge
uv sync
uv run alembic upgrade head
uv run python -m app
# TASK_EXECUTOR=redis 时另开
uv run python -m app.tasks.worker
pnpm dev
```

前端 `apps/knowledge/.env`：`VITE_API_BASE_URL=http://localhost:8012`。访问 http://localhost:8015/knowledge 。Windows 请用 `uv run python -m app`。

可选真实模型联调：在 `services/knowledge/.env` 填入供应商 Key，保持 `MODEL_PROVIDER=openai_compat`，上传文档后看知识库「向量索引」变为就绪，再在检索测试页跑同一问题的三种策略。

## 测试

```bash
cd services/knowledge
uv run pytest -q --tb=short
pnpm --filter @neorvion/knowledge test
pnpm --filter @neorvion/shared test
pnpm --filter @neorvion/shell test
```

测试使用独立库 `neorvion_knowledge_test` 与 mock 模型客户端，不依赖真实 API 计费。

## 性能约束（面向 4 核 4GB）

- 不在服务器常驻本地大模型。
- Embedding 批量走任务，控制批次与 Worker 并发 1。
- 检索在 SQL 层过滤，不把整库 Chunk 载入 Python。
- SQLAlchemy 连接池 `pool_size=5, max_overflow=5`。
- 精确 kNN 适合当前小数据；上万切片后再评估 HNSW，并单独验证多租户过滤召回。

## V4 评测系统

评测不改线上 Chunk / 向量索引。实验只调用 `RetrievalService.search(..., persist_log=False)`，参数快照写入 `evaluation_runs.config_snapshot`。

```text
数据集 → 标注 Chunk（0–3）→ 冻结版本快照 → 创建实验参数方案
→ evaluation_runs QUEUED → Worker 批量检索（可选生成+Judge）
→ 代码计算 Hit/Recall/Precision/MRR/nDCG → 对比 / 调参
```

### 数据集 Schema 与标注

| 表 | 作用 |
| --- | --- |
| `evaluation_datasets` | 数据集元数据、关联知识库、当前冻结版本 |
| `evaluation_dataset_versions` | JSONB 快照：问题、标准答案、标注、`source_key` |
| `evaluation_cases` | 问题。`PENDING` 待标注 / `LABELED` 已标但无有效相关 / `READY` 可正式评测 |
| `evaluation_judgments` | 多 Chunk 标注。`stale=true` 表示切片版本或正文哈希已变 |
| `evaluation_experiments` | 可复用参数方案 |
| `evaluation_runs` | 一次异步执行；PostgreSQL 是状态真相 |
| `evaluation_results` | 单题召回快照、指标、Judge 原始输出 |

`is_unanswerable=true` 是显式无答案题，状态可直接 `READY`，不能当成缺少标注。有监督检索只使用非 stale 且 `relevance>=1` 的 Chunk。

稳定来源键：`kb:{kb_id}:doc:{doc_id}:sha:{sha256}:v:{chunk_version}:i:{chunk_index}`。文档更新导致 Chunk ID 变化时，按哈希/版本把旧标注标 stale，提示人工重确认，禁止悄悄当作有效相关。

导入：CSV / JSONL / 简易 xlsx。中文表头别名：问题、标准答案、类型、难度、标签、无答案。错误行返回 `{row, message}`，成功行写入待标注（无答案题除外）。

### 指标定义（Chunk 粒度，代码计算）

相关集合 R = `{id | relevance >= 1}`。K 是实验配置的最终 Top-K，不是实际返回条数。

| 指标 | 定义 | 例：排名 `[10,99,20]`，相关 `{10:3,20:1,30:2}`，K=3 |
| --- | --- | --- |
| Hit Rate@K | Top-K 是否至少命中一个相关 | 1 |
| Recall@K | \|Top-K ∩ R\| / \|R\| | 2/3 |
| Precision@K | \|Top-K ∩ R\| / K | 2/3 |
| MRR | 第一个相关结果排名的倒数，未命中为 0 | 1 |
| nDCG@K | 增益 `2^rel-1`，折损 `log2(rank+1)` | DCG/IDCG |

Document 粒度单独计算并标记 `granularity=document`，不得与 Chunk 指标混用。无答案题不计算 Recall（分母为零），改为 `false_recall` / `empty_ok` / 拒答率。

`METRIC_VERSION=v4-chunk-ndcg-exp`。

### 生成质量与 Judge 选型

未引入 Ragas：依赖重、与当前 FastAPI/mock 测试栈不契合，且检索指标必须由代码保证数学正确。也未强制 LangSmith。

可选 LLM-as-a-Judge（默认关闭）：Faithfulness / Answer Relevancy / Answer Correctness。无标准答案时 `answer_correctness` 必须为 null。Judge 输出非法 JSON 或越界分数时 **不伪造分数**，只记 `judge_error`。知识库摘录包在 `<untrusted_document>` 中。记录 `judge_model` 与 `judge_prompt_version=v4-judge-1`。结果具有主观性与波动，界面会标明。支持人工 `human_override`。

### 实验可复现

每次运行冻结当前数据集版本。`config_snapshot` 含策略、Top-K、RRF、Rerank、Embedding 模型与维度、Chat/Rerank 模型、Prompt/指标版本。对比时若数据集版本或 Embedding/维度不同，标记 **非严格可比**，不给出误导性提升结论。Chunk Size / Overlap 变化必须通过独立索引版本对比，评测不得改写线上切片。

### 任务与限额

- 单任务最大题量 `EVAL_MAX_CASES`（默认 200）
- Token 预算 `EVAL_TOKEN_BUDGET`
- Worker 并发 `WORKER_CONCURRENCY`
- 同一实验同时只能有一个 QUEUED/RUNNING
- 取消：QUEUED 立即 CANCELLED；RUNNING 设 `cancel_requested`，下一题前退出
- 重试：仅 FAILED/CANCELLED，先删本题结果再入队，`attempt+1`
- 费用：`EVAL_PROMPT_TOKEN_USD` / `EVAL_COMPLETION_TOKEN_USD` 为 0 时不估算，不用假账单

### 检索调优

召回调优页对比 VECTOR / KEYWORD / HYBRID、调整 Vector/Keyword/最终 Top-K 与 RRF k、对比 Rerank 前后排名与阶段耗时。与问答共用 `RetrievalService.search`。

### 本地评测步骤

1. `uv run alembic upgrade head`
2. 上传文档并等待 EMBED 完成
3. 创建数据集 → 新增问题 → 标注相关 Chunk → 冻结（首次运行会自动冻结，之后复用该版本直到再次冻结）
4. 创建实验（先关闭生成评测）→ 运行 → 查看 Recall/nDCG
5. 复制实验、改策略或 Top-K 再跑 → 实验对比
6. 可选打开生成评测（会产生模型费用；测试用 `MODEL_PROVIDER=mock`）

## 已知限制

- 无 OCR、无复杂表格还原。
- 关键词检索不是 BM25；中文主要靠 ILIKE + trigram。
- Rerank 依赖可选兼容 HTTP；未配置则降级。
- 更换 Embedding 维度需要重建向量列。
- LLM Judge 不稳定，不能替代有监督检索指标。
- xlsx 导入只支持简单共享字符串表，复杂 Excel 请改 CSV/JSONL。
- 评测不会为对比自动创建独立向量索引；切片策略变化需另建知识库或重建后再评。

## V5 建议

- 可选 BM25 / 真正的中文分词检索。
- 评测用独立索引版本（按 chunk_size 建影子库）做切片策略 A/B。
- 人工标注工作台：检索候选一键标注、仲裁、一致性检查。
- 可选对接 LangSmith / Ragas，作为旁路而不是核心依赖。
- Token 单价按模型拆分、费用预警。
- 大规模时评估 HNSW，并单独验证多租户 SQL 过滤召回。
