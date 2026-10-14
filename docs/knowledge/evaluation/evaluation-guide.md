# RAG 评测操作指南

本指南对应 Knowledge 微前端，不改 Shell 的 Wujie 保活。切租户后带 ID 的详情页会回到模块安全页。

## 1. 怎么在页面选择评测数据集

1. 左侧 **质量与运营 → 评测数据集**（路由 `/datasets`）。
2. 打开 **V5-RAG-100**。
3. 确认关联了三个测试知识库，且题目 `needs_human_review=待复核`。
4. 可按标注状态筛选：PENDING / LABELED / READY。无答案题会直接 READY。

## 2. 如何运行单道问题

1. 在数据集详情找到题目，点 **单题评测**。
2. 默认跑 HYBRID、Top-K=8、不调用生成模型（避免费用）。
3. 弹出层展示 `stages`、召回 Chunk、Recall/MRR/nDCG（有标注时）。
4. 若要生成回答，请到 **检索评测** 创建实验并打开 `evaluate_generation`，不要批量勾选全部 100 题。

## 3. 如何选择 VECTOR、KEYWORD、HYBRID

- **召回调优** `/retrieval-test`：同一问题连续跑三种策略，看两路排名。
- **检索评测**：一个实验绑定一种 `strategy`。对比请复制实验后只改策略，再在 **实验对比** 看差异。
- VECTOR 看余弦相似度；KEYWORD 看 simple FTS + trigram（不是 BM25）；HYBRID 看 RRF。

## 4. Top-K 如何调整

实验配置里的 `top_k` 是指标截断 K，也是返回条数上限。`candidate_k` 是融合前候选。增大 K 通常提高 Recall、降低 Precision。先固定 K 再改策略，否则对比不公平。

## 5. Rerank 如何启用

实验或召回调优打开 `rerank`。模型不可用时 `rerank_degraded=true`，结果退回融合序。对比 Rerank 开关时，其他参数必须一致。

## 6. 如何判断检索结果是否正确

1. 看召回 Chunk 是否覆盖标注的 `chunk_id`（或同文档关键句）。
2. 无答案题：不应把无关 Chunk 当证据，模型应拒答。
3. 失效标注（stale）不能当有效相关。先点 **刷新失效标注**。
4. 待复核题即使指标好看，也要人读一遍标准答案。

## 7. Recall@K、Precision@K、MRR、nDCG 的含义

代码定义在 `app/evaluation/metrics.py`，禁止用 LLM 给这些分。

| 指标 | 含义 |
| --- | --- |
| Hit@K | Top-K 是否至少命中一个相关 Chunk |
| Recall@K | Top-K ∩ 相关 / 全部相关。相关集合为空时不算 |
| Precision@K | Top-K ∩ 相关 / K（K 是配置截断） |
| MRR | 第一个相关结果排名的倒数，未命中为 0 |
| nDCG@K | 用 0–3 相关性分，增益 `2^rel-1`，折损 `log2(rank+1)` |

无答案题看拒绝率和是否仍召回大量内容，不要看 Recall。

## 8. Chunk Size 和 Overlap 如何影响结果

更小的 Size 更精确但易把答案拆开（多 Chunk 题 Recall 难）；更大的 Size 上下文完整但噪声多、向量被稀释。Overlap 过小会丢跨段句子，过大则重复、浪费。本评测默认字符级 800/120。

## 9. 什么情况下需要重新切片、重新 Embedding

- 改 Size / Overlap / 策略：必须重新切片，再 Embedding。
- 只改切片正文：标记 STALE，重建该 Chunk 向量。
- 换 Embedding 模型或维度：全量重建索引；换维度还要新迁移或新库。
- 更新文档：先快照，解析成功前旧 ACTIVE 仍可检索；发布新版本后旧标注可能 stale。

## 10. 如何比较不同实验

1. 冻结数据集版本，保证两次 run 题目一致。
2. 每次只改一个变量（策略 / K / Rerank / 切片）。
3. 打开 **实验对比**，看指标差和低分问题。
4. `stale_judgment_count>0` 时对比不可严格复现。

## 11. 如何分析检索失败

按 [04-troubleshooting.md](../../../services/knowledge/eval_fixtures/docs/general/04-troubleshooting.md)：文档未完成、切片停用、向量未 READY、授权名单、回收站、中文 KEYWORD 弱、维度不一致。对照 VECTOR 与 KEYWORD 哪一路缺失。

## 12. 如何记录问题与改进方案

可复制：

```text
题目编号：
策略 / Top-K / Rerank：
是否召回标准 Chunk：
失败类型：切错 / 召不回 / 排太低 / 幻觉 / 跨库串台
改进：改切片 / 补文档 / 改题 / 开 Rerank / 换 HYBRID
人工结论：通过 / 不通过 / 需改标准答案
```

不要把待复核的 AI 答案直接当成最终真理。
