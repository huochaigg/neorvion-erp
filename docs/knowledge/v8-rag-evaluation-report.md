# Neorvion Knowledge V8 RAG 优化与评测技术报告

- 范围：V8 核心开发与评测收尾。本文只整理真实源码、数据库落库记录、冻结快照与历史实验结果。
- 环境：租户 `3`；评测主数据集 `#10` `V8-R2-120-Comprehensive`；第二轮语料知识库 `#8` `V8-R2-Multi-Chunk`（8 篇文档、80 个 `ACTIVE` Chunk）。
- 指标版本：检索 `METRIC_VERSION=v4-chunk-ndcg-exp`；证据覆盖 `EVIDENCE_COVERAGE_VERSION=v1-fact-or-and`。二者在 V8 收尾期内未改公式。
- 约束：不改写历史 Run 39～53；不把不同冻结版本的结果直接比较；不把 R2-08 离线回放当成一次新的生成评测。
- 费用：所有 Run 的 `estimated_cost_usd` 均为 `null`。平台 `EVAL_PROMPT_TOKEN_USD` / `EVAL_COMPLETION_TOKEN_USD` 为 `0` 时不估算账单，下文只报落库 Token，不编造美元费用。

---

## 一、项目架构

Knowledge 是独立 RAG 服务：FastAPI（`8012`）+ PostgreSQL / pgvector + Redis。身份与租户以 IAM 为权威来源；本服务校验 RS256 JWT，读 Redis 授权快照。前端意愿头 `X-Tenant-ID` 不能单独采信。

```text
浏览器 → Shell 8015 → IAM 8010
                 ↘ Knowledge 微前端 8017 → Knowledge API 8012
                                              ├ PostgreSQL + pgvector
                                              ├ Redis（授权快照 / 任务队列）
                                              ├ 本地文件目录
                                              └ OpenAI 兼容 Chat / Embedding；DashScope Rerank
Knowledge Worker → Redis 队列（task_id 或 eval:{run_id}）→ 同一套 PG
```

### 1.1 文档解析、Chunk、Embedding

| 环节 | 实现 |
| --- | --- |
| 解析 | PDF（pypdf，扫描件明确失败，无 OCR）、DOCX、Markdown、TXT |
| 切片 | 字符单位；默认 `chunk_size=800`、`chunk_overlap=120`；`FIXED` / `RECURSIVE`；新版本成功后再把旧 `ACTIVE` 标为 `SUPERSEDED` |
| 关键词列 | `search_tsv = to_tsvector('simple', content)` + GIN，另有 `pg_trgm`。**不是 BM25** |
| 向量 | `chunk_embeddings` 一行一片；记录模型、维度、内容哈希、`chunk_version`；只检索当前模型、当前维度、`READY`、且与文档 `active_chunk_version` 匹配的行 |
| 默认 Embedding | 百炼 `text-embedding-v4`，1024 维 |
| 检索算法 | 当前规模走精确余弦 kNN，**不建 HNSW** |

第二轮评测语料在知识库 `#8`，8 篇 Markdown：

| 文档 ID | 文件 |
| --- | --- |
| 38 | `01-sales-outbound.md` |
| 39 | `02-purchase-receipt-return.md` |
| 40 | `03-inventory-reserve-transfer.md` |
| 41 | `04-after-sale-refund.md` |
| 42 | `05-iam-tenant-rbac.md` |
| 43 | `06-knowledge-rag-evaluation.md` |
| 44 | `07-cross-domain-state-collisions.md` |
| 45 | `08-shipment-stocktake.md` |

### 1.2 检索与 Rerank

三种策略共用 `RetrievalService.search`。智能搜索、召回调优、RAG Chat、评测不得分叉实现。

| 策略 | 实现 |
| --- | --- |
| `VECTOR` | 查询向量 + pgvector 余弦距离，相似度 = `1 - distance` |
| `KEYWORD` | PostgreSQL `simple` FTS + `pg_trgm` + 中文 `ILIKE` |
| `HYBRID` | 两路召回后 RRF（`k=60`）按 `chunk_id` 去重融合 |

可选 Rerank：默认 `qwen3-rerank`（DashScope 原生 rerank，不是 Chat Completions）。模型不可用或抛错时降级到融合结果，并打 `rerank_degraded`。分数不混用：向量相似度、关键词分、RRF、Rerank 各自独立。

**租户与授权过滤全部在 SQL `WHERE` 中完成**（`tenant_id`、知识库 ACTIVE、切片 ACTIVE+enabled、当前版本、指定知识库 ID）。禁止先全局召回再在 Python 里丢弃其他租户。

### 1.3 RAG Chat、Context Builder、LLM Judge

线上问答链路：

```text
问题 → 检索 → 可选 Rerank → pack_prompt_hits → build_rag_messages → LLM（SSE）
```

- Chat 与评测 GENERATE 共用 `pack_prompt_hits` / `build_rag_messages`。标准答案只进 Judge Prompt，不进被评测生成 Prompt。
- 证据字符上限 `chat_max_context_chars=6000`。整片纳入或整片丢弃，不做半片截断。
- 文档正文包在 `<untrusted_document>` 中；系统提示要求忽略摘录里的指令。
- 无足够依据时明确拒答，不把猜测当知识库事实。
- LLM 调用期间不持有长事务：先落库用户/助手消息并 commit，再流式生成。
- 默认 Chat / Judge 模型：`deepseek-flash`。Judge 版本在生成评测中为 `v5-r2-06`。非法 JSON 或越界分数不伪造分数，只记 `judge_error`。

收尾时代码的打包版本是 `CONTEXT_PACK_VERSION=v2-skipover-dedup`。**Run 53 生成时仍是当时的打包与观测代码**；R2-08 之后的可观测字段和 skip-over 行为，不能回写到 Run 53 的历史指标上。

### 1.4 多租户、异步任务、断点续跑

- 功能权限：`knowledge:read/create/update/delete`。检索与问答需要 read。
- 知识库另有 `KnowledgeBaseGrant`。非所有者即使有功能权限，也不一定能读某一本库。
- 文档任务：`PARSE` / `CHUNK` / `EMBED`。PostgreSQL 是状态真相；Redis List 只投递任务 ID。
- 评测与文档任务共用 Worker，前缀 `eval:` 区分。同一 Run 用 `lease_owner` / `lease_until` 保证同一时刻只有一个 Worker。
- 评测阶段 checkpoint：`RETRIEVE` → `RERANK` → `GENERATE` → `JUDGE` → `METRICS`。Rerank 不是第二次检索。
- 暂停、取消、租约过期后的恢复：已落库题目保留；Token 累计来自 `evaluation_results.usage`，恢复不从 0 重算。Judge 失败时可复用已生成回答。
- 超时请求可能已产生供应商费用，续跑不能保证绝对不重复计费。

---

## 二、评测体系

### 2.1 数据集 #10 与冻结 v1～v4

数据集 `#10` `V8-R2-120-Comprehensive`，120 题，Case ID `229`～`348`。四次冻结均钉住知识库 `[8]`：

| 冻结版本 | 创建时间 | 题目数 | 无答案题 | 标注条数 | 平均每题标注 | 非 stale 相关性分布 |
| --- | --- | --- | --- | --- | --- | --- |
| v1 | 2026-10-24 14:23:54 +08 | 120 | 15 | 877 | 7.31 | rel1=261，rel2=307，rel3=309 |
| v2 | 2026-10-24 16:12:46 +08 | 120 | 15 | 877 | 7.31 | 与 v1 相同 |
| v3 | 2026-10-24 16:31:50 +08 | 120 | 15 | 126 | 1.05 | rel2=41，rel3=85 |
| v4 | 2026-10-24 16:36:03 +08 | 120 | 15 | 126 | 1.05 | rel2=40，rel3=86 |

v1/v2 把大量相关切片标进 Recall 分母；v3/v4 按 R2-04 收口为 canonical primary（及少量 alternative / partial）。**同一套检索，换冻结版本后 Hit / Recall / nDCG / Coverage 都会变，不能直接比较。**

工作稿改标注不影响已冻结快照。历史 Run 钉住当时的 `dataset_version`。

### 2.2 120 道题的题型与 Ground Truth

冻结 v4 的 `question_type`：

| 类型 | 题数 | 说明 |
| --- | --- | --- |
| `FACTUAL` | 36 | 单点事实 |
| `HALLUCINATION` | 15 | 错误前提，知识库有纠正证据 |
| `LONG` | 15 | 长问 / 多约束 |
| `MIXED_LANG` | 15 | 中英混写、字段名、错误码 |
| `MULTI_DOC` | 11 | 跨文档 |
| `MULTI_CONDITION` | 10 | 同文档多条件或多切片 |
| `PARAPHRASE` | 3 | 改写提问 |
| `UNANSWERABLE` | 15 | 知识库无答案；`answer_correctness` 必须为 null |

设计桶（题目 `tags` 中的 `bucket:`，与 `question_type` 不是同一字段）：

| 设计桶 | 题数 | 其中无答案 |
| --- | --- | --- |
| factual | 15 | 0 |
| hard | 20 | 0 |
| multi | 20 | 0 |
| precision | 15 | 0 |
| long | 15 | 0 |
| hallucination | 15 | 0 |
| regression | 5 | 0 |
| unanswerable | 15 | 15 |

Ground Truth 收口规则（R2-04，冻结 v4）：

- 必要事实写在 `required_facts` 与 `fact:` / `primary:` / `alt:` / `partial:` 标签。
- 同一 fact：primary 或 alternative 命中任一即覆盖（OR）。
- 多个 required_facts 必须分别覆盖（AND）。
- `partial` 不算完整覆盖。
- 无答案题不进入有监督检索宏平均，也不计算 Evidence Coverage。
- 错误前提题（`HALLUCINATION`）有标准纠正答案，计入 Correctness，并单独看 `false_premise_identified` / `correction_correctness`。

### 2.3 80 ACTIVE Chunk

知识库 `#8` 当前 `ACTIVE` Chunk = **80**，文档 = **8**。评测检索 SQL 只使用该库、当前版本、ENABLED 切片。第一轮小语料在知识库 `#7`（13 篇 / 13 个 ACTIVE Chunk），与 `#8` 不是同一索引，不能横比。

### 2.4 检索指标（代码计算，禁止 LLM 打分）

相关集合 \(R = \{id \mid relevance \ge 1\}\)。K 是实验配置的最终 Top-K，不是实际返回条数。无答案题不调用 `retrieval_metrics`。

| 指标 | 定义 |
| --- | --- |
| Chunk Hit@K | Top-K 是否至少命中一个相关项 |
| Chunk Recall@K | \(\lvert TopK \cap R \rvert / \lvert R \rvert\) |
| Precision@K | \(\lvert TopK \cap R \rvert / K\) |
| MRR | 第一个相关结果排名的倒数；未命中为 0 |
| nDCG@K | 增益 \(2^{rel}-1\)，折损 \(\log_2(rank+1)\) |

Document 粒度必须单独调用并标明 `granularity=document`，不得与 Chunk 指标混用。

无答案题改记：

- `false_recall`：Top-K 非空则 1（检索到了无关段落，不等于模型编造）。
- `empty_ok`：Top-K 为空。
- 生成阶段另看拒答，不能把 `false_recall` 当幻觉率。

### 2.5 Evidence Coverage 与 Complete Evidence Rate

`v1-fact-or-and`。按必要事实覆盖，**不改写** Chunk Recall / nDCG。

- Evidence Coverage：被覆盖的 required facts 比例，宏平均只对可监督题。
- Complete Evidence Rate：该题全部 required facts 均被覆盖的比例。
- 检索侧覆盖看 Top-K；Prompt 侧覆盖只看实际进入生成 Prompt 的切片。

### 2.6 Prompt Evidence Coverage

与检索 Coverage 使用同一套 fact 标签，分母相同，分子改为 `in_prompt=true` 的切片。因此：

- 金标进了 Top-K 但被 6000 字预算整片丢弃 → 检索 Coverage 高、Prompt Coverage 低。
- 相关切片在 Prompt 里、但不是 canonical primary → 模型仍可能答对，Prompt Coverage 仍可为 0。

### 2.7 生成与 Judge 指标

| 指标 | 来源 | 口径 |
| --- | --- | --- |
| Faithfulness | LLM Judge | 是否忠于本次 Prompt 摘录 |
| Correctness | LLM Judge | 相对标准答案；无答案题必须为 null |
| Relevancy | LLM Judge | 是否切题 |
| Citation Validity | 代码 | `[n]` 是否落在本次 Prompt |
| Gold Citation Match | 代码 | 引用是否命中 primary/alternative；**不是真实引用正确率** |
| Claim Support | 未评测 | 引用是否支持具体主张；界面与 Run 53 均标明 `not_evaluated` |
| 无答案拒答 | Judge `refused` | 15 题单独算 Refusal Accuracy，不用关键词启发式冒充 |
| 错误前提纠正 | Judge | `false_premise_identified` + `correction_correctness` |
| fabricated_terms | 代码 | 无答案题的确定性编造检查；拒答复述题面数字不算编造（R2-08 修复后的代码；Run 53 快照仍可能误报） |

Judge 失败不得伪造分数。结果具有主观性，不能替代有监督检索指标，也不能替代人工抽检。

---

## 三、实验过程

**不同冻结数据集版本的结果不能直接比较。** 下文按可比组叙述；跨组只谈方法，不谈“提升了多少个点”。

另有 Run 43（实验 `#9` `v8-05-Long-Query`，数据集 `#7` 冻结 v2，3 题，KB `#7`），不属于本报告对照序列，不列入主表。

### 3.1 Run 39～42：第一轮小语料检索比较

- 数据集：`#3` `V8-01-Hard-Cases` **冻结 v2**（不是数据集 #10 的 v2）。
- 知识库：`#7` `测试知识库`，13 个 ACTIVE Chunk。
- 题量：5 道难题。无答案题 0。
- 配置共性：Top-K=8，Candidate-K=24，RRF k=60，Embedding `text-embedding-v4` / 1024d，`evaluate_generation=false`，`metric_version=v4-chunk-ndcg-exp`。
- 时间：2026-10-22。

小语料上每个文档往往只有 1 个 ACTIVE 切片，Top-K 8 容易饱和，四种策略差异会被候选池淹没。这是后来单独建设多 Chunk 知识库 `#8` 的原因。

### 3.2 Run 44～47：120 题四种检索策略对照

- 数据集：`#10` **冻结 v1**。
- 知识库：`#8`，80 ACTIVE Chunk。
- 题量：120；有监督 105；无答案 15。
- 配置共性：Top-K=8，Candidate-K=24，RRF k=60，KB `[8]`，生成与 Judge 全部未开。
- 时间：2026-10-24 14:24 起。四次运行 Case ID 完全一致（229–348）。

只比较策略：`VECTOR` / `KEYWORD` / `HYBRID` / `HYBRID+Rerank`。

**不能与 Run 48～53（冻结 v4）比 Recall 涨跌。** v1 平均每题 7.31 条相关标注，Recall 分母大；v4 收口到约 1.05 条，分母小。

### 3.3 Run 48～51：Top-K / Candidate-K 消融

- 数据集：`#10` **冻结 v4**。
- 策略固定 `HYBRID`，RRF k=60，无 Rerank，无生成。
- 四组：T5/C24、T8/C24、T12/C24、T8/C48。
- 时间：2026-10-24 16:59 起并行。

这是 V8 检索侧最终对照组。Run 49 与随后的 Run 53 检索配置相同（HYBRID T8/C24），检索宏平均一致。

### 3.4 Run 52：10 题生成烟测

- 实验 `#28` `V8-R2-06-HYBRID-T8-C24-GEN-SMOKE-10`。
- 数据集 `#10` **冻结 v4**。HYBRID T8/C24，Rerank 关，生成开。
- `case_ids`：229、244、259、264、284、299、314、316、329、331（8 道可监督 + 2 道无答案）。
- Chat / Judge：`deepseek-flash`，`judge_prompt_version=v5-r2-06`，当时 `generation_metric_version=v1-gen-r2-06`。
- 目的：验证 GENERATE + JUDGE 流水线可跑通，不是 120 题结论。

### 3.5 Run 53：120 题完整生成评测

- 实验 `#29` `V8-R2-06-GENERATION-FULL-120`。
- 数据集 `#10` **冻结 v4**。HYBRID T8/C24，Rerank 关。
- 120 题全量；Chat + Judge 各 120 次。
- 当时 `generation_metric_version=v2-gen-r2-06`。
- 时间：2026-10-24 17:56:10～18:07:54（约 11 分 45 秒），`attempt=1`，`SUCCESS`。

这是 V8 唯一一次 120 题真实生成评测。R2-08 的代码修复与离线回放 **没有** 改写本 Run 的 `metrics` / `usage` / 单题结果。

---

## 四、真实实验结果

下列数字全部来自 `evaluation_runs.metrics` / `usage` 及已落库单题字段。未重新计算公式，未调用模型。

### 4.1 Run 39～42（数据集 #3 冻结 v2，KB #7，n=5）

| 项 | Run 39 | Run 40 | Run 41 | Run 42 |
| --- | --- | --- | --- | --- |
| 实验 | #16 向量 | #17 关键词 | #18 混合 | #19 混合+Rerank |
| 策略 | VECTOR | KEYWORD | HYBRID | HYBRID + Rerank |
| 状态 | SUCCESS | SUCCESS | SUCCESS | SUCCESS |
| Hit@8 | 1.0 | 1.0 | 1.0 | 1.0 |
| Recall@8 | 1.0 | 0.9333 | 1.0 | 1.0 |
| Precision@8 | 0.375 | 0.35 | 0.375 | 0.375 |
| MRR | 1.0 | 1.0 | 1.0 | 1.0 |
| nDCG@8 | 0.9620 | 0.9700 | 0.9540 | 1.0 |
| P50 / P95（ms） | 3128 / 3447 | 33 / 45 | 3308 / 16776 | 5451 / 32827 |
| Embedding | api=1，cache=0，12 tokens | 无 | 未记 api | 未记 api |
| Chat / Judge | 0 | 0 | 0 | 0 |
| 费用估算 | null | null | null | null |

结论：5 题小语料上 Hit/MRR 饱和。KEYWORD 漏了部分相关切片（Recall 0.9333）。Rerank 把 nDCG 拉到 1.0，但 P95 从混合检索的 16.8s 升到 32.8s。该组只能说明“单切片语料会掩盖策略差异”，不能外推到 120 题。

### 4.2 Run 44～47（数据集 #10 冻结 v1，KB #8，n=120 / 有监督 105）

| 项 | Run 44 VECTOR | Run 45 KEYWORD | Run 46 HYBRID | Run 47 HYBRID+Rerank |
| --- | --- | --- | --- | --- |
| 状态 | SUCCESS | SUCCESS | SUCCESS | SUCCESS |
| Hit@8 | 0.9905 | 1.0 | 1.0 | 1.0 |
| Recall@8 | 0.6216 | 0.5725 | 0.6707 | 0.7142 |
| Precision@8 | 0.5774 | 0.5274 | 0.6060 | 0.6488 |
| MRR | 0.9651 | 0.9191 | 0.9857 | 0.9852 |
| nDCG@8 | 0.7390 | 0.6943 | 0.7876 | 0.8612 |
| P50 / P95（ms） | 84 / 188 | 149 / 233 | 175 / 323 | 2345 / 3303 |
| 墙钟 | 35.3 s | 43.5 s | 44.7 s | 342.2 s |
| Embedding | api=2，cache=118，42 tokens | api=0 | api=0，cache=120 | api=0，cache=120 |
| Rerank | 0 | 0 | 0 | success=119，degraded=1 |
| Chat / Judge | 0 | 0 | 0 | 0 |
| 无答案 false_recall | 1.0 | 1.0 | 1.0 | 1.0 |
| empty_ok | 0.0 | 0.0 | 0.0 | 0.0 |
| 费用估算 | null | null | null | null |

本组可比结论：

- HYBRID 全面优于单路。KEYWORD 的 Hit@8=1.0，但 Recall / nDCG 最低：能碰到一个相关切片，收不齐 v1 的大标注集合。
- Rerank 相对纯 HYBRID：Recall +0.0435，nDCG +0.0736；P50 从 175 ms 升到 2345 ms（约 13.4 倍），墙钟从 45 s 升到 342 s。有 1 题 Rerank 降级。
- 15 道无答案题 Top-K 均非空。知识库里本就有仓库/库存段落，检索返回它们不等于幻觉。

### 4.3 Run 48～51（数据集 #10 冻结 v4，HYBRID 消融，n=120 / 有监督 105）

| 项 | Run 48 T5/C24 | Run 49 T8/C24 | Run 50 T12/C24 | Run 51 T8/C48 |
| --- | --- | --- | --- | --- |
| 状态 | SUCCESS | SUCCESS | SUCCESS | SUCCESS |
| Hit@K | 0.8571 | 0.9429 | 0.9524 | 0.9333 |
| Recall@K | 0.8175 | 0.8984 | 0.9175 | 0.8889 |
| Precision@K | 0.1905 | 0.1298 | 0.0889 | 0.1286 |
| MRR | 0.6206 | 0.6329 | 0.6338 | 0.6137 |
| nDCG@K | 0.6482 | 0.6756 | 0.6816 | 0.6634 |
| Evidence Coverage | 0.8698 | 0.9254 | 0.9444 | 0.9127 |
| Complete Evidence Rate | 0.8381 | 0.8952 | 0.9238 | 0.8857 |
| P50 / P95（ms） | 350 / 504 | 368 / 532 | 344 / 514 | 354 / 511 |
| Embedding cache | 120 | 120 | 120 | 120 |
| 无答案 false_recall | 1.0 | 1.0 | 1.0 | 1.0 |
| 费用估算 | null | null | null | null |

本组可比结论：

- T5 → T8：Hit +0.0857，Recall +0.0810，Coverage +0.0556。T8 → T12：Hit 只再 +0.0095，Recall +0.0190，Coverage +0.0190，Precision 继续下降（分母变大，不是检索变差）。
- **Candidate-K 从 24 扩到 48，T8 上全面略降**（Hit 0.9429→0.9333，Recall 0.8984→0.8889，Coverage 0.9254→0.9127，nDCG 0.6756→0.6634）。更大候选池把噪声送进 RRF，并不自动提高 Top-K 质量。
- 推荐检索配置：**HYBRID Top-K=8 / Candidate-K=24 / RRF k=60 / 不默认开 Rerank**。这就是 Run 49 / Run 53 的检索侧。

### 4.4 Run 52（冻结 v4，10 题烟测）

| 项 | 落库值 |
| --- | --- |
| 状态 / 进度 | SUCCESS / 100 |
| 有监督 / 无答案 | 8 / 2（配置抽了 2 道无答案；数据集快照 meta 仍写着全集 15） |
| Hit@8 / Recall@8 / nDCG@8 | 0.875 / 0.875 / 0.7079 |
| Evidence Coverage / Complete | 0.875 / 0.875 |
| Faithfulness | 1.0（n=10） |
| Correctness | 1.0（n=8） |
| Relevancy | 0.99（n=10） |
| Prompt Coverage | 0.875 |
| Refusal Accuracy | 1.0（n=2） |
| 错误前提识别 / 纠正 | 1.0 / 1.0（n=2） |
| fabricated_unanswerable_count | **2**（314 误报「面积」；316 误报「热线」「工作时间」） |
| prompt_truncated_rate | 0.0 |
| Token | prompt 59593 + completion 3302，非估算 |
| P50 / P95（usage 口径） | 119 / 133 ms（检索侧；生成墙钟约 65 s） |
| 费用估算 | null |

结论：流水线可跑通，8 道可监督题 Judge 全对。无答案题已经正确拒答，但当时的 `fabricated_terms` 把拒答里复述的题面词当成编造。这直接推动了后续规则收紧；**烟测 10 题不能外推 120 题 Correctness。**

### 4.5 Run 53（冻结 v4，120 题完整生成）——V8 生成基线

检索宏平均与 Run 49 相同（同一冻结、同一 HYBRID T8/C24）：

| 检索指标 | 值 | n |
| --- | --- | --- |
| Hit@8 | 0.9429 | 105 |
| Recall@8 | 0.8984 | 105 |
| Precision@8 | 0.1298 | 105 |
| MRR | 0.6329 | 105 |
| nDCG@8 | 0.6756 | 105 |
| Evidence Coverage | 0.9254 | 105 |
| Complete Evidence Rate | 0.8952 | 105 |
| 无答案 false_recall / empty_ok | 1.0 / 0.0 | 15 |

生成与引用（`evaluation_runs.metrics.generation`，`generation_metric_version=v2-gen-r2-06`）：

| 指标 | 值 | n | 说明 |
| --- | --- | --- | --- |
| Faithfulness | 0.9931 | 120 | 110 题 =1.0；最低 0.7（277） |
| Correctness | 0.9814 | 105 | 97 题 =1.0；&lt;0.8 的 3 题：277、295、238 |
| Relevancy | 0.9929 | 120 | |
| Prompt Evidence Coverage | 0.9032 | 105 | 低于检索 Coverage 0.9254 |
| Citation Validity | 1.0 | 113 | 编号均落在本次 Prompt |
| Gold Citation Match | 0.4136 | 105 | 不是真实引用正确率 |
| citation_correctness（兼容字段） | 0.4136 | 105 | 等于 Gold Match |
| Claim Support | null | — | `not_evaluated` |
| Refusal Accuracy | 1.0 | 15 | 15/15 拒答 |
| 错误前提识别 | 1.0 | 15 | 15/15 |
| 纠正正确率 | 1.0 | 15 | 15/15 |
| fabricated_unanswerable_count | 1 | — | 仅 323，题面「300」「50」误报 |
| prompt_truncated_rate | **0.0** | 120 | **观测 bug，见第六节；不是真的零截断** |
| Judge 失败 / 跳过 | 0 / 0 | | |

由已落库单题字段汇总、非重新跑评测（R2-07 只读分析）：

| 项 | 值 |
| --- | --- |
| Prompt Complete Evidence Rate | 0.8762（n=105） |
| 检索 Complete | 0.8952（与 Run 指标一致） |
| generate_calls / judge_calls | 120 / 120 |
| 检索 P50 / P95 | 116.0 / 154.1 ms |
| 生成 P50 / P95 | 2497.5 / 5854.7 ms |
| Judge P50 / P95 | 2358.0 / 5099.3 ms |
| 单题端到端 P50 / P95 | 5143.5 / 8870.5 ms |
| usage.latency_p50 / p95 | 117 / 154 ms（该字段是检索延迟，不是端到端） |
| Token | prompt **696198** + completion **33852**，`token_estimated=false` |
| Token 预算 | 1000000；未打满 |
| Embedding | api=0，cache=0（HYBRID 查询向量走缓存/既有调用，本 Run usage 未再记 embedding token） |
| 墙钟 | 2026-10-24 17:56:10.142 → 18:07:54.876（约 704 s） |
| 费用估算 | **null** |

Correctness 最低的可监督题（落库 Judge 分）：277=0.4，295=0.4，238=0.7，313=0.85，283=0.9。其余可监督题均 ≥0.9。

**Run 53 主要结论（仅对本冻结、本配置、本一次生成）：**

1. 检索 Hit@8=0.9429 时，生成 Correctness 仍有明显失败题；答对不等于金标进了 Top-K。
2. 无答案 15/15 拒答，错误前提 15/15 识别并纠正。生成侧的主要风险不是胡编面积/热线，而是检索缺失导致的过拒答，以及金标被 Prompt 预算挤出。
3. Gold Match 0.41 与 Validity 1.0 同时成立：模型引用的是 Prompt 里的合法编号，但不总是 canonical 金标切片。
4. `prompt_truncated_rate=0` 与 118 题实际整片 omitted 矛盾，属于当时 GENERATE 过滤 `in_prompt=false` 后再打包的观测错误。历史数字保持原样，不在本报告里改写。

---

## 五、重点案例

全部取自 **Run 53** 落库结果 + 冻结 v4 标签。259、264 在本 Run 中生成成功，仍按指定清单分析，因为它们是多事实题的对照，不是失败编造。

### 229 · FACTUAL · Coverage=0 但 Correctness=1.0

- **问题：** 销售订单还停在 DRAFT 时，仓库那边会不会已经先把货预占掉？
- **期望：** 不会。创建和保存 DRAFT 只写订单自己的表，未预占库存。
- **检索：** Hit=0，Recall=0，Coverage=0。必要事实 `draft-no-reserve` 的 primary 是 Chunk **#63**，未进 Top-K。Top-K：70、138、129、64、62、71、65、139（均为销售/碰撞/盘点相关）。
- **Prompt：** 前 7 片进入；#139 整片 omitted。Prompt Coverage=0。
- **生成：** 明确回答「不会」，并引用草稿未预占、确认才预占。
- **Judge：** F=1.0，C=1.0，R=1.0，Validity=1.0，Gold Match=0.0。
- **根因：** 金标切片过窄。相邻销售切片已经写明 DRAFT 不预占，模型读到了等价证据；Coverage 按 primary=#63 计 0，Correctness 按语义计 1。这是 **GT 颗粒度问题，不是生成幻觉**。
- **改进：** 把 #62/#64/#70 等等价段落标为 alternative；或接受 Coverage 与 Correctness 解耦。不要为了抬 Coverage 去改历史冻结。

### 238 · FACTUAL · 检索缺失导致答案不完整

- **问题：** 调拨单号前缀是什么？
- **期望：** `TR` + 年份 + 6 位 id。
- **检索：** Hit=0，Coverage=0。primary `tr-prefix=#88` 未进 Top-K。Top-K 以调拨/碰撞/盘点切片为主（93、129、134…），#91 整片 omitted。
- **Prompt：** 无金标。Prompt Coverage=0。
- **生成：** 只写出前缀 `TR`，没有年份和 6 位 id。
- **Judge：** F=0.9，C=0.7，R=0.85。
- **根因：** 精确字段题对 KEYWORD/HYBRID 的字面命中敏感；金标切片未召回，模型只能复述 Prompt 里出现的 `TR`。
- **改进：** 检索侧提高错误码/前缀类精确匹配；生成侧在证据只有部分字段时保持不完整声明，而不是补全。这不是打包问题，R2-08 回放 Prompt 未变化。

### 249 · FACTUAL · 金标在 Rank 8 被预算挤出，相关切片仍够用

- **问题：** 采购退货单上的 `WAITING_OUTBOUND` 和销售订单确认后的 `WAITING_OUTBOUND`，是不是同一个含义？
- **期望：** 不是。同名不同业务、库存含义不同。
- **检索：** Hit=1.0，Recall=1.0，Coverage=1.0，MRR=0.125。primary `#77` 在 **Rank 8**。
- **Prompt：** `#77` 因预算整片 omitted；进入的是 89、124、102、128、101、129、81。Prompt Coverage=0，Complete=false。
- **生成：** 正确区分销售已预占 vs 采购退货等待供应商取货、未扣库存。
- **Judge：** F=0.95，C=1.0，R=1.0，Gold Match=0.0。
- **根因：** Top-K 命中但 Context Builder 按检索顺序装入，排在最后的金标装不进 6000 字。交叉域碰撞文档的相邻切片已经足够回答。
- **改进：** skip-over 不能把 `#77` 装进去（块本身超过剩余预算）。需要更大预算、更短切片，或接受「相关切片可替代 primary」。R2-08 回放该题 Prompt 未变。

### 259 · MULTI_DOC · 生成成功的跨文档对照

- **问题：** 售后 `WAITING_REFUND` 和采购退货 `WAITING_REFUND`，能不能当成同一种退款状态机？
- **期望：** 不能。客户退款与供应商退款是两套单据、权限、错误码。
- **检索：** Hit=1.0，Recall=1.0，Coverage=1.0，Complete=true。事实 `two-refunds=#102`、`refund-no-stock=#82` 均在 Prompt 中；#101 整片 omitted。
- **生成：** 分列 `refund:confirm` / `REFUND_EXCEEDS_APPROVED` 与 `supplier_refund:confirm` / `SUPPLIER_REFUND_EXCEEDS_APPROVED`，并声明售后状态机细节证据不足、不臆测。
- **Judge：** F=1.0，C=1.0，R=1.0，Gold Match=0.5。
- **根因：** 这不是失败。Gold Match 0.5 只说明引用没有覆盖全部 primary，不代表答错。
- **改进：** 保持多事实题的 AND 覆盖定义；不要把 Gold Match 当 Correctness。

### 264 · MULTI_CONDITION · 同文档两切片对照

- **问题：** 销售订单确认时库存怎么变，确认出库时怎么变？两套能不能合成一次扣减？
- **期望：** 确认：quantity 不变、reserved 增加；确认出库：quantity 与 reserved 同减。不能合成一次扣减。
- **检索：** Hit=1.0，Recall=1.0，nDCG=1.0，Coverage=1.0。primary `#63`（确认预占）与 `#66`（出库双减）都在 Prompt 前两名。#133 omitted。
- **生成：** 分阶段写清，并说明确认只是占用、出库才是货离开仓库。
- **Judge：** F=1.0，C=1.0，R=1.0，Gold Match=0.5。
- **根因：** 成功案例。同文档多切片只要都进 Prompt，模型能完成对比。
- **改进：** 无紧急项。它证明 Coverage=1 且证据进 Prompt 时，生成可以稳定。

### 277 · MULTI_CONDITION · 证据在 Prompt 里却过拒答

- **问题：** 为什么第一轮每个文档往往只有 1 个 ACTIVE 切片，第二轮多 Chunk 语料不能写进同一知识库？
- **期望：** 第一轮 Top-K 8 容易饱和；多 Chunk 应导入独立库，避免覆盖已冻结 Run 使用的库；历史 Run 钉住 `dataset_version`。
- **检索：** Hit=1.0，Coverage=1.0，Complete=true。primary `#121` 同时承载 `isolate-kb` 与 `pin-version`，Rank 1 且在 Prompt 中。#117 omitted。
- **生成：** 引用了「不要覆盖已冻结 Run 使用的库」和 `dataset_version`，但声称「知识库对该细节证据不足」，把能回答的部分收成拒答。
- **Judge：** F=0.7，C=0.4，R=0.65，`refused=true`，Gold Match=1.0。
- **根因：** **不是检索失败，是生成过保守。** 系统提示「证据不足就拒答」在证据其实足够时被过度触发。Gold Match=1 说明它引用了金标，却仍说证据不足。
- **改进：** 拒答策略需要与“摘录已覆盖 required facts”对齐；可在评测报告里把过拒答单列，不要只看 Faithfulness。打包回放该题无变化。

### 283 · MULTI_DOC · 三事实只召回一部分

- **问题：** 售后占用的是已出库数量，采购退货占用的是已收货数量，它们占用的都是 `reserved_quantity` 吗？
- **期望：** 不是同一套占用。售后看已出库可退；采购退货打 available；`reserved_quantity` 是销售预占。
- **检索：** Hit=1.0，Recall=0.333，Coverage=0.667，Complete=false。未覆盖 `inv-reserved`（primary **#83** 未进 Top-K）。`prt-no-sales-res=#78` 在 Prompt；`as-occupy` primary #100 未进 Top-K，alternative #101 在 Rank 8 且 **omitted**。Prompt Coverage=0.333。
- **生成：** 方向正确（三种占用不同），但对采购退货是否「完全不是 reserved」的边界写得偏满。
- **Judge：** F=0.95，C=0.9，R=0.97，Gold Match=0.167。
- **根因：** 跨三文档事实，Top-K=8 装不下全部 primary；剩下的又被预算挤出。Coverage 0.667 仍可能得到 C=0.9，因为部分证据加模型归纳够用，但不稳定。
- **改进：** 多文档 AND 事实是 Top-K 与预算的共同上限。不要用 Candidate-K=48 硬扩（Run 51 已显示无效）。可考虑按文档去重后的配额，而不是按 GT 换切片。

### 295 · MIXED_LANG · 金标未进 Top-K，模型过拒答

- **问题：** 确认出库记账流水的 `type` 和 `reference_type` 是什么？
- **期望：** `type=OUTBOUND`，`reference_type=OUTBOUND_ORDER`，`change_quantity` 为负。
- **检索：** Hit=0，Coverage=0。primary `#66` 未进 Top-K。Top-K 被售后/调拨/盘点切片占据；#89 omitted。
- **Prompt：** 无出库流水金标。模型从无关摘录里看到 `type=OUTBOUND` 的只言片语，看不到 `OUTBOUND_ORDER`。
- **生成：** 承认 `reference_type` 证据不足并拒答，同时写出了 `type=OUTBOUND`。
- **Judge：** F=0.9，C=0.4，R=0.8，`refused=true`。
- **根因：** 精确英文字段题 + 金标未召回。过拒答使 Correctness 掉到 0.4。R2-08 回放 Prompt 未变。
- **改进：** 检索要能把 `OUTBOUND_ORDER` 所在切片打进 Top-K；生成在只看到部分字段时应标「部分可知」，与完全无据拒答分开计分。

### 313 · LONG · 检索不全 + 语料与 GT 争议

- **问题：** 错误码 40097 在仓库停用、承运商校验、销售仓库停用、发运停用、门店创建停用等路径是否都是同一业务含义，`data.error` 分别是什么？
- **期望：** 40097 会被复用，必须看 `data.error`；仓库/门店停用多为 `WAREHOUSE_DISABLED`；承运商路径是另一套校验，不能把仓库停用当成唯一含义。
- **检索：** Hit=1.0，Recall=0.5，Coverage=0.5。`c40097` 的 alternative `#131` 在 Prompt，primary `#130` Rank 8 omitted；`st-wh` primary `#140` / alt `#141` **都未进 Top-K**。
- **生成：** 正确否定「只看 40097」；销售仓库停用写出 `WAREHOUSE_DISABLED`；门店路径声明 `data.error` 证据不足，不编造。
- **Judge：** F=0.95，C=0.85，R=0.95。Judge 说明：标准答案认为门店停用也是 `WAREHOUSE_DISABLED`，模型因摘录没写而拒绝补全。
- **根因：** 长问多路径，Top-K 收不齐；同时 **GT 可能比当前 Prompt 语料更满**。忠实于摘录会在 Correctness 上吃亏。
- **改进：** 补齐 `st-wh` 召回；若语料确实没写门店 `data.error`，应改 GT 而不是强迫模型补全。冻结 v4 保持只读，此项列入 Backlog，不改历史。

### 323 · UNANSWERABLE · 拒答正确，fabricated 误报

- **问题：** 满 300 减 50 要在哪个费用科目维护？
- **期望：** 知识库没有促销满减科目。
- **检索：** 无监督指标。`false_recall=1.0`（Top-K 非空，都是采购/调拨/售后等无关切片）。8 片全部进入 Prompt，本例无 omitted。
- **生成：** 明确「知识库证据不足」，未编造科目。
- **Judge：** F=1.0，Correctness=null，R=1.0，`refused=true`。
- **落库 fabricated：** `true`，`fabricated_terms=['300','50']`，`fabricated_status=likely_fabricated`。这是 **Run 53 当时规则把题面数字当成新型断言**。
- **根因：** 确定性检查未把题面中的价格/数字从 fabricated 集合里排除。拒答复述「满 300 减 50」不是编造。
- **改进：** R2-08 已改代码：题面数字、中文数字、价格、电话不记入 fabricated。**未回写 Run 53**，因此历史上 `fabricated_unanswerable_count=1` 保持不变。

### 339 · HALLUCINATION · 金标 omitted，相关切片仍完成纠错

- **问题：** 取消出库释放预占时如果数字写大了，是不是也报 `OUTBOUND_EXCEEDS_RESERVED`？
- **期望：** 释放超额是 `INSUFFICIENT_RESERVED_INVENTORY`；`OUTBOUND_EXCEEDS_RESERVED` 是出库超过预占。
- **检索：** Hit=1.0，Coverage=1.0，MRR=0.125。primary `#64` 在 Rank 8。
- **Prompt：** `#64` 整片 omitted。进入 85、72、71、65、128、126、101。Prompt Coverage=0。
- **生成：** 指出前提错误，给出正确错误码，并区分出库超预占路径。
- **Judge：** F=1.0，C=1.0，R=1.0，`false_premise_identified=true`，`correction_correctness=1.0`，Gold Match=0.0。
- **根因：** 与 249 同类——金标在队尾被预算丢掉，库存预占文档的其他切片已写明两套错误码。R2-08 回放 `#64` 仍 omitted。
- **改进：** 错误前提题更依赖「纠正段落是否进 Prompt」，而不是 primary ID。观测上应同时看 Coverage 与 Prompt Coverage，避免以为没截断。

---

## 六、R2-08 最终修复

R2-08 改的是 **新代码与可观测性**。Run 53 的历史指标、单题 Judge、Token、`prompt_truncated_rate=0` **均未被改写**。

### 6.1 截断统计为什么错误

GENERATE 阶段当时把 `in_prompt=false` 的命中滤掉，再交给 `_build_messages`：

1. `pack_retrieved_hits` 已经按 6000 字把装不下的 Chunk 标成 `in_prompt=false`（Run 53 有 118 题至少 omitted 1 片，场均 omitted 1.167）。
2. `_prompt_hit_objects(hits)` 只留下 `in_prompt=true` 的对象送给模型。
3. 第二次打包面对的已经是「一定装得下」的子集，于是 `trace.truncated=False`。
4. 写回的 `prompt_truncated_rate` 因此为 0。前端若只信该字段，会以为没有截断。

这是观测错误，不是「Run 53 真的把 8 片全部送进了 Prompt」。单题 `retrieved[].in_prompt` 一直是对的。

### 6.2 Context Builder 修复方式

收尾代码（`CONTEXT_PACK_VERSION=v2-skipover-dedup`）：

- 按检索顺序尝试整片装入。装不下 **continue** 试下一片，而不是 `break` 丢掉后面所有更短切片。
- 空切片 → `omitted_reason=empty`；同文档近重复（包含关系或 12-gram Jaccard ≥ 0.62）→ `duplicate`；超预算 → `budget`。
- `partially_truncated_chunk_count` 恒为 0：不做半片截断。
- `prompt_observability()` 根据 packed 后的 `in_prompt` 计算 omitted / budget_limited，GENERATE 即使仍只把 `in_prompt` 切片发给模型，侧指标也会标出预算受限。
- Chat 与评测共用同一函数，**不读 Ground Truth / required_facts / gold**。

### 6.3 整片 omitted 与半片截断的区别

| | 整片 omitted | 半片截断 |
| --- | --- | --- |
| V8 行为 | 采用 | **不采用** |
| 含义 | 该 Chunk 正文不进入 Prompt | 进入 Prompt 但尾巴被切掉 |
| 风险 | 金标可能整段缺失（249/339） | 半句规则/错误码被切断，更易导致看似有据的错误回答 |
| 统计 | `omitted_chunk_ids` + `truncation_reason=budget` | `partially_truncated` 在本实现中恒为 0 |

历史 Run 53 的真实情况是整片 omitted，不是半片截断。只是当时的 `prompt_truncated` 没把它记出来。

### 6.4 fabricated_terms 的误报原因

Run 53 的 323：拒答文本复述了题面「满 300 减 50」，检查器把 `300`、`50` 当成 Prompt 中不存在的具体数值。同类误报在 Run 52 的 314（「面积」）、316（「热线」「工作时间」）已经出现。

R2-08 代码改为：题面已出现的数字、中文数字、价格、电话及主题词，在拒答中复述不算编造；不能可靠判断时为 `needs_review`，不强行 `fabricated=true`。中文数字抽取跳过长度 &lt; 2 的 token，避免「统一」里的「一」。

**Run 53 快照未重算**，`fabricated_unanswerable_count=1` 仍是历史值。

### 6.5 120 题离线回放结果

输入：Run 53 已存储的检索 ID 顺序 + 当前 KB #8 正文。不调用 Chat / Judge / Embedding。

| 项 | 历史打包（按存储 in_prompt） | R2-08 skip-over+dedup |
| --- | --- | --- |
| 有 omitted 的题 | 118 | 118 |
| 场均 omitted | 1.167 | 1.117 |
| 场均已用字符 | 5621 | 5657 |
| Prompt Coverage | 0.9032 | 0.9032 |
| Prompt Complete | 0.8762 | 0.8762 |
| Coverage 回退题 | — | 0 |
| 多装入一片的题 | — | 6：237、239、260、270、275、330 |
| 249 的 #77 / 339 的 #64 | 仍 omitted | 仍 omitted |

这只说明 **在同一批检索结果上，新打包多塞进了 6 个更靠后的短切片，没有降低 Prompt Coverage**。它 **不是** 新的 120 题生成评测，不能更新 Faithfulness / Correctness / Token。

### 6.6 为什么撤回激进的 Chunk 替换方案

回放中还试过两类未合入的方案（均已撤回，未改主路径）：

- 同文档多样性优先：约 91 题 Prompt 被改写，Prompt Coverage **下降约 0.95 个百分点**。
- 无约束的队尾替换/修补：约 118 题被改写，Prompt Coverage **下降约 3.5 个百分点**。

评测打包不能看 gold。按「同文档换一片」优化，会把已经覆盖事实的切片换出去。因此最终只保留 skip-over + 同文档近重复去重。

### 6.7 哪些遗留问题没有解决

- 249 / 339：金标仍在 Rank 8，6000 字装不下。
- 238 / 295：金标根本不在 Top-K，打包救不了。
- 229：GT primary 过窄，相关切片已能答对。
- 277：证据在 Prompt 仍过拒答。
- 283：三文档事实收不齐；#83 未召回，#101 被挤出。
- 313：`st-wh` 未召回；GT 与语料是否一致仍待人工。
- Claim Support 仍未评测。
- Run 53 的 `prompt_truncated_rate=0` 与 `fabricated_unanswerable_count=1` 保持历史原样。
- 没有授权过「修复后重新跑 120 题 Chat+Judge」，因此 **不能声称 R2-08 已经提高了 Correctness**。

**明确：Run 53 的历史指标未被改写。修复后新代码的效果与历史 Run 53 不能混同为一次新生成评测。**

---

## 七、工程经验与面试总结

### 为什么 Hit@K 高不代表答案准确

Hit 只问 Top-K 里有没有任意一个 `relevance≥1` 的切片。Run 53 Hit@8=0.9429，但 238/295 金标未命中导致 C=0.4～0.7；277 金标命中且进 Prompt，C 仍为 0.4。Hit 是检索下限指标，不是答案正确率。

### 为什么 Chunk Recall 不等于 Evidence Coverage

Recall 的分母是所有 `relevance≥1` 的切片；Coverage 的分母是 `required_facts`。v1 每题平均 7.31 条相关，Recall 被分母压到 0.62～0.71；v4 收口到约 1.05 条，同样 HYBRID T8 的 Recall 变成 0.898。283 可以 Hit=1 而 Coverage=0.667：碰到了一个相关切片，但三件必要事实只齐了两件。

### 为什么 Candidate-K 越大不一定越好

Run 51 把候选从 24 扩到 48 后，Hit / Recall / nDCG / Coverage 全部略降。RRF 在更大噪声池里重排，真正相关的切片不一定更靠前。扩大候选必须用同一冻结做对照，不能凭直觉加。

### Rerank 的实际收益和延迟代价

仅在 **冻结 v1** 的 Run 46 vs 47：nDCG 0.7876→0.8612，Recall 0.6707→0.7142；P50 175→2345 ms，墙钟 45→342 s，且有 1 次降级。第一轮 5 题上 nDCG 0.954→1.0，P95 再翻倍。V8 最终生成评测 **没有开 Rerank**：在 T8/C24 已经 Coverage 0.925 时，13 倍延迟换不到生成阶段已验证的收益。

### Top-K 与 Prompt 字符预算的关系

Top-K=8 是检索截断；6000 字是生成截断。两者同时存在时，Rank 8 的金标经常进不了 Prompt（249、339）。T12 还能再抬一点检索 Coverage（0.944），但会把更多字符竞争送进打包器，Precision 降到 0.089。生成默认应对齐「检索 Top-K × 单片长度 ≈ 预算」，而不是把 K 加到预算明显装不下。

### Ground Truth 质量如何影响指标

- 把噪声标成 1：Recall 分母变大。
- 漏标真正相关：命中看起来像失败。
- 只标一个过窄的 primary：Coverage=0 但模型能答对（229）。
- 标准答案比语料更满：忠实模型会被 Correctness 扣分（313）。
- 冻结版本就是为了防止工作稿改标后悄悄改写历史 Run。

### 为什么 Judge 不能完全替代人工审核

Run 53 的 Judge 给 277 打了 C=0.4（合理），给 229 打了 C=1.0（语义对，但 Coverage 暴露 GT 问题），给 323 的 Faithfulness=1.0（对）同时代码误报 fabricated。Judge 有主观性、会跟标准答案而不是语料走，也不会检查观测 bug。有监督检索指标必须由代码保证；生成结论必须抽检失败题。

### 无答案和错误前提如何分别评估

| | 无答案 | 错误前提 |
| --- | --- | --- |
| 知识库 | 没有该事实 | 有纠正证据 |
| 检索 | 不进 Recall；看 false_recall / empty_ok | 按普通可监督题算 Hit/Recall/Coverage |
| 生成期望 | 拒答，Correctness=null | **不能只拒答**，要指出前提错误并给出正确规则 |
| Run 53 | 15/15 拒答；false_recall 全 1 | 15/15 识别且纠正正确 |

检索到无关仓库段落（false_recall=1）不等于编造。Run 52/53 的 fabricated 误报，说明「拒答文本里出现了题面数字」不能当幻觉。

### 如何设计可恢复、可追踪的评测流水线

1. 先冻结数据集，Run 钉住 `dataset_version` + `config_snapshot`（策略、K、模型、指标版本、KB ID）。
2. 阶段 checkpoint + 租约；崩溃后从题目中断阶段续跑，Token 从已落库 usage 累计。
3. 检索指标代码化；生成指标与观测字段分开，避免第二次打包覆盖第一次截断。
4. Chat 与评测共用 Context Builder，禁止评测偷看 gold。
5. 对比前检查冻结版本、Embedding 模型/维度、KB ID；不可比就不要输出「提升」。
6. 费用单价为 0 时输出 `null`，不用假账单。超时可能已计费，续跑不能承诺零重复调用。

---

## 八、最终验收

### 已完成能力

- 多租户知识库 CRUD、文档解析/切片/向量索引、回收站与授权。
- VECTOR / KEYWORD / HYBRID + 可选 Rerank 的统一检索引擎。
- RAG Chat（SSE、引用、拒答、上下文预算）。
- 评测数据集、冻结快照、实验/Run、异步 Worker、暂停恢复、Token 预算。
- Chunk 粒度 Hit / Recall / Precision / MRR / nDCG（`v4-chunk-ndcg-exp`）。
- Evidence Coverage / Complete Evidence（`v1-fact-or-and`）。
- 生成评测：Judge v5、Citation Validity / Gold Match 拆分、无答案拒答、错误前提纠正。
- R2-08：截断可观测、skip-over 打包、fabricated 题面数字修复、离线回放与单测。

### 已验证能力

- 小语料 5 题四种策略（Run 39～42，数据集 #3 v2）。
- 120 题四种检索策略（Run 44～47，**冻结 v1**）。
- 120 题 T/C 消融（Run 48～51，**冻结 v4**）。
- 10 题生成烟测（Run 52）与 120 题完整生成（Run 53，冻结 v4，HYBRID T8/C24）。
- 无答案拒答 15/15、错误前提纠正 15/15（Run 53 落库）。
- 在 Run 53 的检索快照上，新打包不降低 Prompt Coverage（离线回放，非生成评测）。

### 尚未验证能力

- R2-08 之后 **重新跑** 120 题 Chat+Judge 的 Faithfulness / Correctness / Token。
- 生成阶段开启 Rerank 的质量与延迟（只有检索阶段的 Run 47）。
- Top-K=12 进入生成后，预算竞争对 Correctness 的真实影响。
- Claim Support。
- BM25 / 中文分词、HNSW、OCR、复杂表格。
- 独立影子索引上的 chunk_size / overlap A/B。
- 多模型（非 `deepseek-flash`）Judge 一致性。

### 已知限制

- 关键词检索不是 BM25；无 OCR。
- 精确 kNN，不建 HNSW；换 Embedding 维度要重建向量列。
- 6000 字整片打包会丢掉 Rank 靠后的金标。
- Judge 主观，不能替代人工；Gold Match 不是引用正确率。
- 无答案题检索几乎总是非空（false_recall=1.0）。
- 历史 Run 53 的截断率和 fabricated 计数含已知观测/规则缺陷，且保持原样。
- `estimated_cost_usd` 全程为 null，本报告不编造账单。
- 评测超时可能已向供应商计费；续跑不保证零重复。

### 后续 Backlog（不在 V8 范围，不启动）

1. 授权后的新 120 题生成 Run（新 experiment，不覆盖 53），用于验证 R2-08 打包与 fabricated 修复。
2. 失败题检索：238/295 前缀与 `OUTBOUND_ORDER`；283 的 `#83`；313 的 `st-wh`。
3. GT 工作稿：229 等价切片、313 语料一致性。下一冻结版本另开，不改 v1～v4。
4. 过拒答（277）与部分字段题的计分拆分。
5. Claim Support 的可靠实现或明确永久不做。
6. 可选 BM25、影子索引切片实验、按模型拆分的真实单价。

---

## V8 最终技术总结

V8 把 Neorvion Knowledge 从「能检索」收成一套 **可冻结、可续跑、可分指标解释** 的 RAG 评测系统。检索、打包、生成、Judge 被拆开测量：Hit 高不等于答对，Recall 不等于事实覆盖，Top-K 命中不等于进了 Prompt，引用编号合法不等于引用了金标。

在第二轮 120 题、冻结 v4、HYBRID Top-K=8 / Candidate-K=24、80 ACTIVE Chunk 上，检索 Coverage 0.925、生成 Correctness 0.981、无答案拒答与错误前提纠正均为 15/15。真正还没闭合的，是精确字段召回、Prompt 预算与队尾金标、过拒答，以及 **用一次新的生成 Run 去验证 R2-08 代码**——而不是改写 Run 53。

V8 到此收尾。不再开启新的开发版本；历史冻结与历史 Run 保持只读。
