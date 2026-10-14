# 通用知识评测题（30）

标注状态：AI 生成、待人工复核。无答案题已标 expected_no_answer。

## gen-001

- 问题：Knowledge API 成功时响应 code 是多少？
- 标准答案：0。
- 知识库：通用知识库
- 来源文档：01-python-fastapi.md
- Chunk 线索：code=0（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：api
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-002

- 问题：Repository 层可以自行 commit 吗？
- 标准答案：不可以。Service 负责提交。
- 知识库：通用知识库
- 来源文档：01-python-fastapi.md
- Chunk 线索：Repository 不, commit（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：architecture
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-003

- 问题：查询必须带什么租户条件？
- 标准答案：必须带 tenant_id。
- 知识库：通用知识库
- 来源文档：01-python-fastapi.md
- Chunk 线索：tenant_id（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：tenant
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-004

- 问题：为什么 Pydantic 用 extra=forbid？
- 标准答案：防止客户端改 tenant_id 等不允许字段。
- 知识库：通用知识库
- 来源文档：01-python-fastapi.md
- Chunk 线索：extra=forbid（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：pydantic
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-005

- 问题：上传文件为何不用裸 File(...)？
- 标准答案：为避免 B008，使用 Annotated[UploadFile, File()]。
- 知识库：通用知识库
- 来源文档：01-python-fastapi.md
- Chunk 线索：Annotated[UploadFile, File()]（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：fastapi
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-006

- 问题：请求体多了不允许字段通常返回什么状态码？
- 标准答案：422。
- 知识库：通用知识库
- 来源文档：01-python-fastapi.md
- Chunk 线索：422（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：http
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-007

- 问题：Knowledge 的关键词检索是 BM25 吗？
- 标准答案：不是。simple FTS + trigram + 中文片段 ILIKE，不是 BM25。
- 知识库：通用知识库
- 来源文档：02-postgres-redis.md
- Chunk 线索：不是 BM25（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：retrieval
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-008

- 问题：默认向量维度和测试库维度分别是多少？
- 标准答案：默认 1024，测试库 8。
- 知识库：通用知识库
- 来源文档：02-postgres-redis.md
- Chunk 线索：默认 1024, 测试库 8（导入后关联真实 Chunk ID）
- 难度：2　类型：MULTI_CONDITION　有答案：是
- 标签：embedding
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-009

- 问题：只改环境变量能否直接换向量维度？
- 标准答案：不能。必须重建迁移或新开库，并全量重建索引。
- 知识库：通用知识库
- 来源文档：02-postgres-redis.md
- Chunk 线索：更换维度必须重建（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：embedding
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-010

- 问题：解析任务的状态以 Redis 为准还是数据库为准？
- 标准答案：数据库是状态真相，Redis 只投递 task id。
- 知识库：通用知识库
- 来源文档：02-postgres-redis.md
- Chunk 线索：数据库是状态真相（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：task
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-011

- 问题：TASK_EXECUTOR=inline 适合生产吗？
- 标准答案：不适合，仅建议测试。
- 知识库：通用知识库
- 来源文档：02-postgres-redis.md
- Chunk 线索：inline, 仅测试（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：task
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-012

- 问题：切租户会取消已经排队的解析任务吗？
- 标准答案：不会。
- 知识库：通用知识库
- 来源文档：02-postgres-redis.md
- Chunk 线索：不会取消已落库任务（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：task
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-013

- 问题：扫描版 PDF 解析不出字怎么办？当前实现了 OCR 吗？
- 标准答案：任务会提示无文本。当前未实现 OCR。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：扫描版 PDF, OCR（导入后关联真实 Chunk ID）
- 难度：2　类型：MULTI_CONDITION　有答案：是
- 标签：parse
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-014

- 问题：手工改切片正文后向量会怎样？
- 标准答案：标记 STALE 并重建。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：STALE（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：chunk
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-015

- 问题：改 Chunk Size 后只重建向量够不够？
- 标准答案：不够。必须重新切片再 Embedding。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：重新切片再 Embedding（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：chunk
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-016

- 问题：删除文档后检索立刻不可见，文件马上物理删除了吗？
- 标准答案：检索立即不可见，但文件与向量保留到彻底删除。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：回收站, 彻底删除（导入后关联真实 Chunk ID）
- 难度：2　类型：PARAPHRASE　有答案：是
- 标签：recycle
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-017

- 问题：更新文档后、新版本发布前旧切片还能搜到吗？
- 标准答案：能。旧 ACTIVE 切片仍可检索。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：旧 ACTIVE 切片仍可检索（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：version
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-018

- 问题：HYBRID 用什么方式融合两路结果？
- 标准答案：RRF。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：RRF（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：hybrid
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-019

- 问题：无答案题为什么不按普通题看 Recall？
- 标准答案：相关集合为空时不计算 Recall，考察拒绝编造。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：is_unanswerable, 不计算 Recall（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：eval
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-020

- 问题：API Key 能通过改 X-Tenant-Id 访问别的企业吗？
- 标准答案：不能，不匹配则 403。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：不能改绑其他租户（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：apikey
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-021

- 问题：Embedding 返回 401 应该自动猛重试吗？
- 标准答案：不应该。401/402 不要盲目重试。
- 知识库：通用知识库
- 来源文档：04-troubleshooting.md
- Chunk 线索：401/402, 不要盲目重试（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：embed
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-022

- 问题：Embedding 429 能否重试？
- 标准答案：可以。
- 知识库：通用知识库
- 来源文档：04-troubleshooting.md
- Chunk 线索：429/5xx, 可重试（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：embed
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-023

- 问题：检索为空时要检查切片和向量的哪些状态？
- 标准答案：切片 ENABLED 且 ACTIVE；向量 READY 且 model_name 匹配。
- 知识库：通用知识库
- 来源文档：04-troubleshooting.md
- Chunk 线索：ENABLED, READY（导入后关联真实 Chunk ID）
- 难度：3　类型：MULTI_CONDITION　有答案：是
- 标签：retrieval
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-024

- 问题：AI 生成的标准答案能直接当生产评测基准吗？
- 标准答案：不能，带 needs_human_review。
- 知识库：通用知识库
- 来源文档：04-troubleshooting.md
- Chunk 线索：needs_human_review（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：eval
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-025

- 问题：不想跑整页实验时，页面上哪里可以只测一道题？
- 标准答案：数据集详情点“单题评测”。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：单题评测（导入后关联真实 Chunk ID）
- 难度：2　类型：FACTUAL　有答案：是
- 标签：eval
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-026

- 问题：资源不存在和不属于当前租户对外有何共同点？
- 标准答案：都表现为不可访问（404）。
- 知识库：通用知识库
- 来源文档：01-python-fastapi.md
- Chunk 线索：404, 不可访问（导入后关联真实 Chunk ID）
- 难度：2　类型：PARAPHRASE　有答案：是
- 标签：tenant
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-027

- 问题：外键为什么始终带 tenant_id？
- 标准答案：保证切片、向量、文档与知识库同属一个企业。
- 知识库：通用知识库
- 来源文档：02-postgres-redis.md
- Chunk 线索：复合外键, tenant_id（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：db
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-028

- 问题：请说明 KEYWORD、HYBRID 以及改切片后索引失效的关系。
- 标准答案：KEYWORD 是 simple FTS+trigram+中文片段 ILIKE，不是 BM25；HYBRID 用 RRF；改切片会 STALE 需重建，改切参要重新切片。
- 知识库：通用知识库
- 来源文档：01-python-fastapi.md, 02-postgres-redis.md, 03-ops-faq.md, 04-troubleshooting.md
- Chunk 线索：simple FTS, RRF, STALE（导入后关联真实 Chunk ID）
- 难度：4　类型：LONG　有答案：是
- 标签：retrieval
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-029

- 问题：知识库被授权名单排除会导致什么检索现象？
- 标准答案：检索为空或该库不可选。
- 知识库：通用知识库
- 来源文档：04-troubleshooting.md
- Chunk 线索：授权名单（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：acl
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## gen-030

- 问题：智能搜索支持哪三种策略？
- 标准答案：VECTOR、KEYWORD、HYBRID。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md
- Chunk 线索：VECTOR / KEYWORD / HYBRID（导入后关联真实 Chunk ID）
- 难度：1　类型：FACTUAL　有答案：是
- 标签：search
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____
