# 常见技术问题排查

## Embedding 失败

- 401/402：密钥无效或欠费，不要盲目重试。
- 429/5xx：可重试。任务页点重试。
- 维度不一致：查询向量与索引维度不同，需要按当前 `EMBEDDING_DIMENSIONS` 重建索引。

## 检索为空

1. 文档是否 COMPLETED。
2. 切片是否 ENABLED 且 ACTIVE。
3. 向量是否 READY 且 model_name 匹配。
4. 知识库是否被授权名单排除。
5. 知识库或文档是否在回收站。

## 评测指标异常

- Recall 分母是全部相关 Chunk。漏标会导致虚高或虚低。
- 无答案题不要按普通题看 Recall。
- AI 生成的标准答案带 `needs_human_review`，不能直接当生产基准。
