# PostgreSQL、pgvector 与 Redis

## PostgreSQL / SQLAlchemy

Knowledge 使用独立 PostgreSQL。V3 检索依赖 `pgvector` 扩展。向量列维度由迁移时的 `EMBEDDING_DIMENSIONS` 决定，默认 1024，测试库 8 维。更换维度必须重建迁移或新开库。

全文检索使用 `to_tsvector('simple', content)`，另有 `pg_trgm`。这不是 BM25。中文主要靠 ILIKE 与 trigram。

复合外键始终带 `tenant_id`。

## Redis

解析、切片、向量化任务：数据库是状态真相，Redis List 只投递 task id。`TASK_EXECUTOR=redis` 时 API 入队，Worker 执行；`inline` 仅测试。切页面或切租户不会取消已落库任务。

评测 run 同样入队。取消只对 QUEUED/RUNNING 有效。
