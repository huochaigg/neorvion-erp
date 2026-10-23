# 知识库检索、切片与评测边界

Neorvion Knowledge 是独立服务。身份以 IAM 为权威来源。模型密钥只在 Knowledge 服务端环境变量中，不返回前端，也不写入 Git。评测不修改线上 Chunk 或向量索引。

## 文档处理任务

`PARSE` / `CHUNK` / `EMBED` 是不同任务。PostgreSQL 是真相；Redis List 只投递 `task_id` 或 `eval:{run_id}`。

| 类型 | 库 | 说明 |
| --- | --- | --- |
| PDF | pypdf | 无文本视为扫描版，明确失败，错误码 40075，不做 OCR |
| DOCX | python-docx | 保留 Heading 与段落 |
| Markdown | 文本 + 标题识别 | 保留 ATX 标题 |
| TXT | charset-normalizer | 常见编码 |

上传单文件上限 `max_upload_bytes` 默认为 20MB，单次最多 `max_upload_files` 10 个。超过 `pdf_page_warn`（默认 80）只在 warning 中提示，没有页数硬拒绝。

`PARSE` / `CHUNK` 失败会影响文档状态。`EMBED` 失败不回滚已完成的原文和切片。文档 RUNNING 任务在 Worker 重启后标失败；评测 RUNNING 在租约过期后改为 QUEUED，保留已落库题目并从中断阶段续跑。

## 切片参数

切片单位是字符（Python `len`），不是 Token。策略：`FIXED` 或 `RECURSIVE`。默认 `RECURSIVE`。

| 参数 | 默认 | 约束 |
| --- | --- | --- |
| `default_chunk_size` | 800 | `chunk_size_min` 100 到 `chunk_size_max` 8000 |
| `default_chunk_overlap` | 120 | 必须小于 `chunk_size`，且不能为负 |

`RECURSIVE` 分隔符顺序为空行、单行换行、中文句号、叹号、问号、分号、逗号、空格，最后才按字符切开。重新切片写入新 `version`，成功后再把旧 `ACTIVE` 标为 `SUPERSEDED`。禁用切片不删向量，但检索 SQL 排除 `enabled=false`。

## 向量索引

查询与文档必须同一 Embedding 模型与维度。默认 `text-embedding-v4`，1024 维。更换模型后旧向量不参与检索，需重建索引。更换维度必须重建迁移或新开库。

检索只使用当前模型、当前维度、`READY`、且 `chunk_version` 与文档 `active_chunk_version` 匹配的行。当前数据规模走精确余弦 kNN（`cosine_distance`），不建 HNSW。小数据加多租户 `WHERE` 过滤时 HNSW 容易降低召回。

关键词路是 PostgreSQL `simple` FTS + `pg_trgm` + 中文 `ILIKE`，不是 BM25。`search_tsv` 为 `to_tsvector('simple', content)` 生成列。

查询向量按 `provider + base_url + model + dimensions + 规范化查询文本` 缓存。失败或长度不对的向量不入库。`KEYWORD` 策略不调用 Embedding。

## 三种检索策略

三种策略共用 `RetrievalService.search`。智能搜索、检索测试、问答、评测不得分叉实现。

| 策略 | 英文标识 | 实现 |
| --- | --- | --- |
| 向量 | `VECTOR` | 查询 Embedding + pgvector 余弦，相似度 = `1 - distance` |
| 关键词 | `KEYWORD` | FTS / trigram / ILIKE，不生成查询向量 |
| 混合 | `HYBRID` | 两路召回后 RRF（默认 `rrf_k=60`）按 `chunk_id` 去重 |

默认最终 `top_k=8`，候选 `candidate_k=24`。候选不会小于最终 Top-K。租户、知识库 `ACTIVE`、切片 `ACTIVE+enabled`、当前版本全部在 SQL `WHERE` 中过滤。

可选 Rerank：在融合后的候选上调用独立 Rerank 模型，再截取最终 Top-K。模型不可用或抛错时降级到融合结果，并标记 `rerank_degraded`。`rerank_applied` 表示真正完成了模型重排。

分数不要混用：向量相似度、关键词分、RRF、Rerank 各自独立。阈值只作用在对应一路。

## 问答与拒答

无命中时明确拒答，不把猜测当知识库事实。文档正文包在 `<untrusted_document>` 中，系统提示要求忽略其中的指令。证据字符上限 `chat_max_context_chars`。LLM 调用期间不持有长事务。

SSE 事件：`status` / `token` / `citation` / `done` / `error`。切租户必须 abort 旧 EventStream。前端取消的是浏览器请求，不会取消服务端已落库的解析、索引或评测任务。

## 评测指标由代码计算

`metrics.py` 的 `METRIC_VERSION` 为 `v4-chunk-ndcg-exp`。Hit、Recall、Precision、MRR、nDCG 由代码计算，禁止用 LLM 给这些指标打分。

相关性 0–3 级。`relevance >= 1` 视为相关，会进入 Recall 分母。nDCG 使用增益 `2^rel - 1`。弱相关标签会改变 Recall，标注时必须解释 1 分是否值得纳入正式评测。

无答案题不要调用 `retrieval_metrics`。`false_recall` 只表示 Top-K 非空，定义标记为 `top_k_nonempty_not_hallucination_rate`。它不是幻觉率，也不是错误证据率。

LLM Judge 只产生主观的 Faithfulness、Answer Relevancy、Answer Correctness。Judge 失败时不得伪造分数。

## 实验与运行

实验保存可复用参数，不保存数据集版本。点击运行时把当时的冻结版本钉到 `EvaluationRun.dataset_version`，并把配置拷进 `config_snapshot`。软删除实验不删除历史 Run。

Run 状态：`QUEUED` / `RUNNING` / `PAUSED` / `SUCCESS` / `FAILED` / `CANCELLED`。中断后保留 checkpoint：已成功题目跳过，未完成阶段可续跑。评测 `persist_log=false`，不写线上检索日志。生成评测默认关闭。

同一实验同时只允许一个 `QUEUED` / `RUNNING` / `PAUSED` 的 Run。Worker 通过 `lease_owner` / `lease_until` 保证同一时刻只有一个进程执行。

数据集冻结快照保证历史实验可复现。含失效标注时仍可冻结，但标记非严格可比。已有 Run 的版本不能删除。

## 模型错误不要都叫限流

只有 HTTP 429 或明确的供应商限流文本才能归类 `RATE_LIMIT`。连接失败、DNS、TLS、读超时、5xx、401/403、余额不足各自有错误码。鉴权与配置错误不重试。429 尊重 `Retry-After`。临时网络错误有限指数退避，耗尽后 Run 保持 `PAUSED`，允许人工恢复。

诊断信息保存异常类名、阶段、重试次数、脱敏后的最后错误和请求追踪 ID，不保存 API Key 或请求正文。

## 查询向量缓存

缓存键是 `provider`、解析后的 Base URL、模型名、维度，以及经过 NFKC、空白折叠后的查询文本的 SHA256。不把失败向量、长度不对或含非有限值的向量写入缓存。命中缓存不增加本次 API Token。并发未命中用事务内咨询锁串行化，避免同一查询打两次收费接口。

`KEYWORD` 不得走这条缓存，因为关键词路根本不生成查询向量。文档切片的 Embedding 也不走查询缓存表。

## 实验列表与运行列表

实验列表只展示配置，不把最近一次 Run 的指标写进实验行。运行记录默认按创建时间倒序，可用可选的 `experiment_id` 筛选。软删除实验后，历史 Run 仍显示当时的实验名称。

对比页最多选 2–3 个 `SUCCESS` Run。数据集版本或 Embedding 模型、维度不一致时标记为非严格可比，不给出误导性提升结论。同题诊断按 `case_id` 对齐。有相关标注但未出现在本次 `retrieved` 里，显示「未进 Top-K」。

## Ground Truth 与冻结

工作稿改标注不会改写已经冻结的快照，也不会改写历史 `EvaluationResult`。新 Run 钉的是点击运行时的 `current_version`。因此第一轮 A/B（例如钉在某一版 Hard-Cases 上的 Run）与后来修正过的工作稿可以并存。

`relevance = 0` 的切片会保存在标注表里，但不进入 Recall 分母。SYNTHETIC 噪声文档不得标成 `>=1`。无答案题的相关集合必须为空。

评测 Worker 跳过 `result_status=SUCCESS` 的题目。生成关闭时 `GENERATE` / `JUDGE` 阶段为 `SKIPPED`。Rerank 未启用时 `RERANK` 为 `SKIPPED`。

## 任务失败边界

| 任务 | 失败之后 |
| --- | --- |
| `PARSE` | 文档不能切片 |
| `CHUNK` | 没有可检索正文切片 |
| `EMBED` | 原文和切片保留；该版向量不可用于 VECTOR / HYBRID |

扫描 PDF 无文本：错误码 40075，明确失败，不做 OCR。切片参数不合法：40076。没有可切片文本：40077。重叠长度必须小于切片长度。

默认 Embedding 模型 `text-embedding-v4`、1024 维。测试库使用更低维度。更换维度必须重建迁移或新开库。Rerank 默认 `qwen3-rerank`，走 DashScope 原生 rerank 接口，不是 Chat Completions。

评测运行不写线上 `retrieval_logs`（`persist_log=False`）。召回调优页面的检索可以写日志。两套入口共用 `RetrievalService.search`，不得分叉实现。

Evidence Coverage（多段证据是否被同一道题的 Top-K 覆盖）是后续评测维度建议，当前 `metrics.py` 计算的是 Hit / Recall / Precision / MRR / nDCG，不要把尚未落地的 Coverage 指标说成已有列。

第一轮测试知识库上每个文档往往只有 1 个 ACTIVE 切片，Top-K 8 容易饱和。多 Chunk 语料应导入独立知识库，不要覆盖已冻结 Run 使用的库。

## 模型配置与密钥

平台级 Chat / Embedding / Rerank 来自环境变量。API 只返回 `has_api_key` 与 `api_key_env`，永不返回密钥。普通租户管理员不能覆盖平台密钥。连通测试需要 `knowledge:update`。

`CHAT_API_KEY` 可回退 `DEEPSEEK_API_KEY`；`EMBEDDING_API_KEY` / `RERANK_API_KEY` 可回退 `DASHSCOPE_API_KEY`。测试默认 `MODEL_PROVIDER=mock`，不产生计费。连通失败会区分密钥缺失、URL 错误、模型不存在、余额不足、维度不一致。摘要不含密钥。

问答只保留最近若干轮历史，证据字符上限 `chat_max_context_chars`。LLM 调用期间不持有长事务：先落库用户/助手消息并 commit，再流式生成，最后再写结果与 citation。

知识库另有资源 ACL：`KnowledgeBaseGrant`。非所有者即使有 `knowledge:read`，也不一定能读某一本库。检索 SQL 的租户与授权过滤全部在 `WHERE` 中完成，禁止先全局召回再在 Python 里丢弃其他租户。

评测数据集冻结后，历史 Run 钉住 `dataset_version`。工作稿改标注不影响已冻结快照。第一轮 V8-01～V8-07 的冻结版本和 Run 39～42 应保持只读。

## 切片长度实验为什么需要多 Chunk 语料

默认 `chunk_size=800`、`chunk_overlap=120`。后续有效字符大约每片 680。短文档会整篇落进 1 个切片，VECTOR / KEYWORD / HYBRID / Rerank 的差异会被「候选池只有十几行」淹没。

多 Chunk 导入后，同一结论可能落在相邻切片的重叠区，也可能被标题切开。评测应观察：精确错误码是否仍能被 KEYWORD 命中；跨章节规则是否需要更大 overlap 或 Rerank 才能同时进入 Top-K。不要为了把切片数凑到某个整数而复制段落。

标注相关性 0–3。只有 `>=1` 进入 Recall 分母。nDCG 增益为 `2^rel - 1`。把噪声文档标成 1 会扩大分母、压低 Recall。把本应相关的切片漏标会让真正命中的结果看起来像失败。工作稿修正不得改写已冻结版本。


