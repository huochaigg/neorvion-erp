# PostgreSQL、pgvector 与 Redis

## PostgreSQL / SQLAlchemy

Knowledge 使用独立 PostgreSQL。V3 检索依赖 `pgvector` 扩展。向量列维度由迁移时的 `EMBEDDING_DIMENSIONS` 决定，**默认 1024，测试库 8 维**。只改环境变量不能直接换向量维度：更换维度必须重建迁移或新开库，并全量重建索引。

全文检索使用 `to_tsvector('simple', content)`，另有 `pg_trgm`，并对中文查询做片段 ILIKE。**这不是 BM25**，也没有中文专业分词器。

复合外键始终带 `tenant_id`，保证切片、向量、文档与知识库同属一个企业。

## Redis

解析、切片、向量化任务：**数据库是状态真相**，Redis List 只投递 task id。`TASK_EXECUTOR=redis` 时 API 入队，Worker 执行；`TASK_EXECUTOR=inline` **仅建议测试，不适合生产**。切页面或切租户**不会取消**已经落库的解析任务。

评测 run 同样入队。取消只对 QUEUED/RUNNING 有效。
