# V8-R2-120-Comprehensive 质量报告

- 题目数：120
- 题型桶：{'factual': 15, 'hard': 20, 'multi': 20, 'precision': 15, 'long': 15, 'unanswerable': 15, 'hallucination': 15, 'regression': 5}
- 难度：{'EASY': 25, 'MEDIUM': 45, 'HARD': 35, 'EXTREME': 15}
- QuestionType：{'FACTUAL': 37, 'PARAPHRASE': 3, 'MULTI_CONDITION': 2, 'MULTI_DOC': 18, 'MIXED_LANG': 15, 'LONG': 15, 'UNANSWERABLE': 15, 'HALLUCINATION': 15}
- 置信度：{'high': 84, 'medium': 35, 'low': 1}
- 标注状态：{'labeled': 105, 'unanswerable-no-judgment': 15}
- 相关性等级：{'3': 130}
- 需要人工复核：120
- 有效证据切片：54 / ACTIVE 80
- 证据文档分布：{'01-sales-outbound.md': 36, '03-inventory-reserve-transfer.md': 15, '02-purchase-receipt-return.md': 18, '08-shipment-stocktake.md': 11, '06-knowledge-rag-evaluation.md': 14, '04-after-sale-refund.md': 13, '05-iam-tenant-rbac.md': 15, '07-cross-domain-state-collisions.md': 8}
- 07 对照文档被标次数：8
- 近重复对数：0
- 有争议 WAITING_RETURN 取消题：[]
- 失效 Chunk：[]
- 冻结：全部 needs_human_review=True，工作稿未 READY，本轮不冻结
- 数据库：数据集 #10，关联知识库 [8]，current_version=0
- 标注状态（库内）：LABELED 105 / PENDING 15（无答案题无标注）/ READY 0
- Ground Truth：130 条 relevance=3，覆盖 54 个 ACTIVE Chunk、8 份文档
- 幂等：重复执行 created=0、updated=120，不新增题目

## 文档与 Chunk 覆盖

不要求 80 个 Chunk 都成为正相关证据。当前 54/80 有至少一条 rel=3 标注，其余多为状态表 overlap、重复结论或短尾切片。07 对照文档 8 次，没有当成摘要题库来凑覆盖率。

## 04 售后取消

语料文件已改为「只有 PENDING_APPROVAL 可取消」。线上知识库 #8 的 Chunk 103 仍是旧表述（以 AfterSaleService 为准）。本轮未重传、未重新 Embedding。正式题没有使用 WAITING_RETURN 能否取消。

## 需要人工处理

- `r2-fact-009` (medium) 同一句在后续切片有 overlap，需文件名约束
- `r2-fact-014` (medium) 
- `r2-hard-005` (medium) 
- `r2-hard-012` (medium) 
- `r2-hard-013` (medium) 对照文档与领域文档均出现 40097，只标对照文档为 3，避免把所有提及都标成 1
- `r2-hard-015` (medium) “不是 BM25”在切片 overlap 与对照文档重复，导入时必须文件名约束
- `r2-multi-001` (medium) 
- `r2-multi-003` (medium) `Inventory.quantity` 不变 可能出现在出库例子前后，需唯一命中确认章节
- `r2-multi-004` (medium) 第二段证据只用于对照错误码，不把整篇销售文档标 1
- `r2-multi-005` (medium) 
- `r2-multi-006` (medium) 
- `r2-multi-009` (medium) 
- `r2-multi-011` (medium) 
- `r2-multi-012` (medium) system_quantity 句在库存文档与物流文档都有 overlap，优先 08 切片
- `r2-multi-013` (medium) 
- `r2-multi-014` (medium) 
- `r2-multi-016` (medium) 
- `r2-multi-017` (medium) 
- `r2-multi-019` (medium) 第二证据与 hard-015 同源，属可替代证据，不额外标 07
- `r2-multi-020` (medium) 第三句表格分隔符需在切片中原样存在
- `r2-prec-013` (medium) order:audit 在多切片出现，文件名约束后若仍多命中则待复核
- `r2-long-001` (medium) 长问的确认权限在相邻切片，仅标直接支持草稿结论的切片为 3，避免把 overlap 都标 1
- `r2-long-002` (medium) 
- `r2-long-004` (medium) 
- `r2-long-006` (medium) 引文句在切片边界可能被截断，导入时校验完整命中
- `r2-long-007` (medium) 
- `r2-long-009` (low) 标准答案把收货插入出库例子，数字是推导不是原文原句，必须人工复核
- `r2-long-010` (medium) 
- `r2-long-015` (medium) 
- `r2-unan-004` (medium) unit_price 存在，需确认答案强调「建议零售价」缺失而不是单价字段
- `r2-unan-008` (medium) 语料有「不做税、折扣、运费」，若检索命中该句，人工确认仍视为无开票答案而非错误前提
- `r2-unan-011` (medium) SalesOrderSource 含 AMAZON 但不等于有授权协议，保持无答案并待复核
- `r2-unan-013` (medium) 有拣货累计规则，不等于波次 WMS，需人工确认不要误标拣货切片为相关
- `r2-hall-005` (medium) 
- `r2-hall-012` (medium) 若该句落在库存文档切片，以实际命中文件为准
- `r2-regr-002` (medium) 短句可能出现在文首与后文，文件名约束后校验唯一性
