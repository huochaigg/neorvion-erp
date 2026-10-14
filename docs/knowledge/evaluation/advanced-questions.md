# 复杂与边界评测题（10）

标注状态：AI 生成、待人工复核。无答案题已标 expected_no_answer。

## adv-001

- 问题：若订单已确认待出库，此时可用库存如何计算？如果接着出库，quantity 会不会在确认阶段就已经减少？
- 标准答案：待出库时可用 = quantity - reserved。确认阶段 quantity 不减，出库才同时减 quantity 与 reserved。
- 知识库：ERP业务知识库
- 来源文档：02-inventory-reserve.md, 01-sales-order-state.md
- Chunk 线索：RESERVE, WAITING_OUTBOUND, OUTBOUND（导入后关联真实 Chunk ID）
- 难度：4　类型：MULTI_DOC　有答案：是
- 标签：erp, multi-doc
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-002

- 问题：头程还在海上时，能不能把在途数量卖给消费者？如果 ERP 数字更大该听谁的？
- 标准答案：模拟规则下在途不可售。对账以海外仓 WMS 为准。这不是 ERP 已实现海外仓模块。
- 知识库：跨境电商知识库
- 来源文档：01-cross-border-ops.md, 02-exceptions-cs.md
- Chunk 线索：头程在途不计入可售, 以海外仓 WMS 为准（导入后关联真实 Chunk ID）
- 难度：4　类型：MULTI_DOC　有答案：是
- 标签：ecom, multi-doc
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-003

- 问题：同时改了 Embedding 维度和 Chunk Overlap，最少要做哪些步骤才能重新评测？
- 标准答案：维度变更需重建迁移或新开库并全量重建索引；Overlap 变更必须重新切片再 Embedding，然后刷新评测标注失效项。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md, 02-postgres-redis.md
- Chunk 线索：更换维度必须重建, 重新切片再 Embedding（导入后关联真实 Chunk ID）
- 难度：5　类型：MULTI_DOC　有答案：是
- 标签：ops
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-004

- 问题：客户已经退款成功，库存一定通过 RETURN_INBOUND 加回来了吗？请结合售后和库存两份说明。
- 标准答案：不一定。退款成功不等于库存已加回；退货入库才写 RETURN_INBOUND。
- 知识库：ERP业务知识库
- 来源文档：04-shipping-aftersale-rbac.md, 02-inventory-reserve.md
- Chunk 线索：RETURN_INBOUND, 退款与退货状态独立（导入后关联真实 Chunk ID）
- 难度：4　类型：MULTI_DOC　有答案：是
- 标签：aftersale
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-005

- 问题：系统会不会因为安全库存低于阈值就自动生成采购单？
- 标准答案：文档将其列为建议中的规则，当前未作为强制校验/已实现自动采购。
- 知识库：ERP业务知识库
- 来源文档：03-product-purchase-warehouse.md
- Chunk 线索：建议中的规则（导入后关联真实 Chunk ID）
- 难度：3　类型：HALLUCINATION　有答案：是
- 标签：suggested
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-006

- 问题：Amazon 欧洲站当前的佣金百分比是多少？请根据本知识库作答。
- 标准答案：知识库没有真实平台佣金。手册明确不写死佣金比例，不能编造。
- 知识库：跨境电商知识库
- 来源文档：01-cross-border-ops.md
- Chunk 线索：不是某个真实平台现行政策（导入后关联真实 Chunk ID）
- 难度：3　类型：UNANSWERABLE　有答案：否（expected_no_answer）
- 标签：no-answer
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-007

- 问题：现在能不能对扫描件自动 OCR 后入知识库？
- 标准答案：当前未实现 OCR。扫描版 PDF 可能无文本。
- 知识库：通用知识库
- 来源文档：03-ops-faq.md, 04-troubleshooting.md
- Chunk 线索：当前未实现 OCR（导入后关联真实 Chunk ID）
- 难度：3　类型：FACTUAL　有答案：是
- 标签：ocr
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-008

- 问题：一个成员同时属于两个企业时，把 A 企业 Token 配上 B 的 X-Tenant-Id 能读 B 的库存吗？
- 标准答案：不能单靠 Header。必须经成员关系校验；不匹配则 403/404，且不泄露资源是否存在。
- 知识库：ERP业务知识库
- 来源文档：05-exceptions.md, 04-shipping-aftersale-rbac.md
- Chunk 线索：X-Tenant-Id, 不泄露（导入后关联真实 Chunk ID）
- 难度：4　类型：MULTI_CONDITION　有答案：是
- 标签：tenant
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-009

- 问题：ERP 待出库预占和模拟海外仓预留是不是同一套代码？
- 标准答案：不是。ERP 是国内仓 RESERVE/WAITING_OUTBOUND；海外仓预留是模拟规则，不属于 ERP 已实现模块。
- 知识库：跨境电商知识库
- 来源文档：02-exceptions-cs.md, 01-sales-order-state.md
- Chunk 线索：不要把模拟跨境规则说成 ERP 功能, WAITING_OUTBOUND（导入后关联真实 Chunk ID）
- 难度：5　类型：MULTI_DOC　有答案：是
- 标签：boundary
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____

## adv-010

- 问题：根据知识库，中国人民银行明天将公布的贷款市场报价利率是多少？
- 标准答案：知识库不含该信息，属于无答案问题，不应编造数值。
- 知识库：通用知识库
- 来源文档：04-troubleshooting.md
- Chunk 线索：中国人民银行明天的基准利率（导入后关联真实 Chunk ID）
- 难度：2　类型：UNANSWERABLE　有答案：否（expected_no_answer）
- 标签：no-answer, hallucination
- 审核：待人工复核

评测记录：策略____ K____ Rerank____ 召回是否正确____ 备注____
