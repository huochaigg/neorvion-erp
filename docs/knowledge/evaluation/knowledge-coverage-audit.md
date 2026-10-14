# Knowledge V5 评测知识覆盖审计

范围：租户 3 本地测试环境。未改评测指标，未硬编码检索结果。

## 汇总

- 题目总数：100
- 已有有效证据（真实 Chunk 标注）：98
- 缺少来源文档：0
- 文档存在但缺少有效 Chunk：0
- 有原文但标注缺失：0
- 索引异常：0（三个评测库 ready=total，needs_reindex=false；seed missing_chunks=0）
- 标准答案存在疑问：1（adv-007 曾被误标为无答案，知识库实际写明未实现 OCR，已改为有答案）
- 无答案题：2（adv-006、adv-010；已保持无答案）
- 全部 100 题仍标记 needs_human_review，待人工审核

## 补充或修改的知识文档

- `eval_fixtures/docs/erp/01-sales-order-state.md`（重写，按状态拆段，补全 DRAFT 流转）
- `eval_fixtures/docs/erp/02-inventory-reserve.md`（补全流水类型与确认/出库可用量）
- `eval_fixtures/docs/erp/03-product-purchase-warehouse.md`（采购待收货、退货 WAITING_OUTBOUND）
- `eval_fixtures/docs/erp/04-shipping-aftersale-rbac.md`（售后类型、退款独立、RBAC）
- `eval_fixtures/docs/erp/05-exceptions.md`（拣货/确认出库异常）
- `eval_fixtures/docs/erp/07-outbound-pick.md`（新增：拣货不扣库存）
- `eval_fixtures/docs/ecommerce/01-cross-border-ops.md`、`02-exceptions-cs.md`（扩充模拟规则，保持模拟标记）
- `eval_fixtures/docs/general/01-python-fastapi.md` 至 `04-troubleshooting.md`（补 KEYWORD 中文片段与选错库排查）
- 未改 `06-parse-sample.pdf`；未触碰租户 3 产品手册知识库 1/2

## 索引快照

- ERP业务知识库 id=4 chunks=11 ready=11 pending=0 failed=0 incompatible=0 needs_reindex=False
- 跨境电商知识库 id=5 chunks=3 ready=3 pending=0 failed=0 incompatible=0 needs_reindex=False
- 通用知识库 id=6 chunks=4 ready=4 pending=0 failed=0 incompatible=0 needs_reindex=False

## erp-001 排查结果

- 会话日志根因：检索日志 id=734 显示 HYBRID 但 knowledge_base_ids=[1,2]（产品手册），不是 ERP业务知识库 id=4
- 文档上传：01-sales-order-state.md 已在租户 3 / KB 4，解析 COMPLETED
- DRAFT 规则：切片包含「DRAFT」与「未预占库存」，与 sales_order_state.DRAFT 及 confirm_order 只从 PENDING_CONFIRMATION RESERVE 一致
- Embedding：排查时 chunk_embeddings 为空，VECTOR 路必然为空；本次已按现有流水线重建
- KEYWORD：整句 ILIKE/trigram 不中；FTS 仅匹配 DRAFT 等拉丁词。纯中文题（如 ecom-008）会空召回，已补中文片段 ILIKE
- RRF/Rerank/TopK：正确库上不是把 DRAFT 证据滤掉，而是根本没搜到 ERP 库
- VECTOR 命中：8
- KEYWORD 命中：8
- HYBRID 命中：8
- HYBRID+Rerank 命中：8
- 最终回答：不会。DRAFT 不预占库存；提交仍不预占；确认才 RESERVE。引用 [1] `01-sales-order-state.md` chunk=16。完整策略对照见 `sample-results.md`。
- 检索验证（绑定 ERP 库 id=4）：VECTOR/KEYWORD/HYBRID/HYBRID+Rerank 均召回 8 条，chunk=16 均为第 1；Rerank 分数约 0.986，未把正确证据滤掉。
- 问答验证：probe recall=1.0、hit@1=1.0，回答引用正确来源。

## 逐题覆盖状态

| ID | 状态 | 无答案 | 有效 Chunk | 来源 |
| --- | --- | --- | --- | --- |
| erp-001 | 已覆盖 | 否 | 16,17,18 | 01-sales-order-state.md,01-sales-order-state.md,01-sales-order-state.md |
| erp-002 | 已覆盖 | 否 | 16,20,17 | 01-sales-order-state.md,02-inventory-reserve.md,01-sales-order-state.md |
| erp-003 | 已覆盖 | 否 | 16,17,18 | 01-sales-order-state.md,01-sales-order-state.md,01-sales-order-state.md |
| erp-004 | 已覆盖 | 否 | 17,18 | 01-sales-order-state.md,01-sales-order-state.md |
| erp-005 | 已覆盖 | 否 | 19,20 | 02-inventory-reserve.md,02-inventory-reserve.md |
| erp-006 | 已覆盖 | 否 | 19 | 02-inventory-reserve.md |
| erp-007 | 已覆盖 | 否 | 25,19,20 | 07-outbound-pick.md,02-inventory-reserve.md,02-inventory-reserve.md |
| erp-008 | 已覆盖 | 否 | 20 | 02-inventory-reserve.md |
| erp-009 | 已覆盖 | 否 | 20 | 02-inventory-reserve.md |
| erp-010 | 已覆盖 | 否 | 16,17,18 | 01-sales-order-state.md,01-sales-order-state.md,01-sales-order-state.md |
| erp-011 | 已覆盖 | 否 | 16 | 01-sales-order-state.md |
| erp-012 | 已覆盖 | 否 | 21 | 03-product-purchase-warehouse.md |
| erp-013 | 已覆盖 | 否 | 21 | 03-product-purchase-warehouse.md |
| erp-014 | 已覆盖 | 否 | 21 | 03-product-purchase-warehouse.md |
| erp-015 | 已覆盖 | 否 | 21 | 03-product-purchase-warehouse.md |
| erp-016 | 已覆盖 | 否 | 22 | 04-shipping-aftersale-rbac.md |
| erp-017 | 已覆盖 | 否 | 22 | 04-shipping-aftersale-rbac.md |
| erp-018 | 已覆盖 | 否 | 22 | 04-shipping-aftersale-rbac.md |
| erp-019 | 已覆盖 | 否 | 22 | 04-shipping-aftersale-rbac.md |
| erp-020 | 已覆盖 | 否 | 22 | 04-shipping-aftersale-rbac.md |
| erp-021 | 已覆盖 | 否 | 23 | 04-shipping-aftersale-rbac.md |
| erp-022 | 已覆盖 | 否 | 24 | 05-exceptions.md |
| erp-023 | 已覆盖 | 否 | 24 | 05-exceptions.md |
| erp-024 | 已覆盖 | 否 | 17,18 | 01-sales-order-state.md,01-sales-order-state.md |
| erp-025 | 已覆盖 | 否 | 20,19 | 02-inventory-reserve.md,02-inventory-reserve.md |
| erp-026 | 已覆盖 | 否 | 21 | 03-product-purchase-warehouse.md |
| erp-027 | 已覆盖 | 否 | 22 | 04-shipping-aftersale-rbac.md |
| erp-028 | 已覆盖 | 否 | 16,17,18 | 01-sales-order-state.md,01-sales-order-state.md,01-sales-order-state.md |
| erp-029 | 已覆盖 | 否 | 25,24,21 | 07-outbound-pick.md,05-exceptions.md,03-product-purchase-warehouse.md |
| erp-030 | 已覆盖 | 否 | 24 | 05-exceptions.md |
| ecom-001 | 已覆盖 | 否 | 26,27 | 01-cross-border-ops.md,01-cross-border-ops.md |
| ecom-002 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-003 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-004 | 已覆盖 | 否 | 26,27 | 01-cross-border-ops.md,01-cross-border-ops.md |
| ecom-005 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-006 | 已覆盖 | 否 | 26,27 | 01-cross-border-ops.md,01-cross-border-ops.md |
| ecom-007 | 已覆盖 | 否 | 26,27 | 01-cross-border-ops.md,01-cross-border-ops.md |
| ecom-008 | 已覆盖 | 否 | 26,27 | 01-cross-border-ops.md,01-cross-border-ops.md |
| ecom-009 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-010 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-011 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-012 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-013 | 已覆盖 | 否 | 27 | 01-cross-border-ops.md |
| ecom-014 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-015 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-016 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-017 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-018 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-019 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-020 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-021 | 已覆盖 | 否 | 26,27,28 | 01-cross-border-ops.md,01-cross-border-ops.md,02-exceptions-cs.md |
| ecom-022 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-023 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-024 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-025 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-026 | 已覆盖 | 否 | 27 | 01-cross-border-ops.md |
| ecom-027 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| ecom-028 | 已覆盖 | 否 | 26,27,28 | 01-cross-border-ops.md,01-cross-border-ops.md,02-exceptions-cs.md |
| ecom-029 | 已覆盖 | 否 | 26 | 01-cross-border-ops.md |
| ecom-030 | 已覆盖 | 否 | 28 | 02-exceptions-cs.md |
| gen-001 | 已覆盖 | 否 | 29 | 01-python-fastapi.md |
| gen-002 | 已覆盖 | 否 | 29 | 01-python-fastapi.md |
| gen-003 | 已覆盖 | 否 | 29 | 01-python-fastapi.md |
| gen-004 | 已覆盖 | 否 | 29 | 01-python-fastapi.md |
| gen-005 | 已覆盖 | 否 | 29 | 01-python-fastapi.md |
| gen-006 | 已覆盖 | 否 | 29 | 01-python-fastapi.md |
| gen-007 | 已覆盖 | 否 | 30 | 02-postgres-redis.md |
| gen-008 | 已覆盖 | 否 | 30 | 02-postgres-redis.md |
| gen-009 | 已覆盖 | 否 | 30 | 02-postgres-redis.md |
| gen-010 | 已覆盖 | 否 | 30 | 02-postgres-redis.md |
| gen-011 | 已覆盖 | 否 | 30 | 02-postgres-redis.md |
| gen-012 | 已覆盖 | 否 | 30 | 02-postgres-redis.md |
| gen-013 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-014 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-015 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-016 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-017 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-018 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-019 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-020 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-021 | 已覆盖 | 否 | 32 | 04-troubleshooting.md |
| gen-022 | 已覆盖 | 否 | 32 | 04-troubleshooting.md |
| gen-023 | 已覆盖 | 否 | 32 | 04-troubleshooting.md |
| gen-024 | 已覆盖 | 否 | 32 | 04-troubleshooting.md |
| gen-025 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-026 | 已覆盖 | 否 | 29 | 01-python-fastapi.md |
| gen-027 | 已覆盖 | 否 | 30 | 02-postgres-redis.md |
| gen-028 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| gen-029 | 已覆盖 | 否 | 32 | 04-troubleshooting.md |
| gen-030 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| adv-001 | 已覆盖 | 否 | 16,17,19 | 01-sales-order-state.md,01-sales-order-state.md,02-inventory-reserve.md |
| adv-002 | 已覆盖 | 否 | 28,26 | 02-exceptions-cs.md,01-cross-border-ops.md |
| adv-003 | 已覆盖 | 否 | 31,30 | 03-ops-faq.md,02-postgres-redis.md |
| adv-004 | 已覆盖 | 否 | 22,19,20 | 04-shipping-aftersale-rbac.md,02-inventory-reserve.md,02-inventory-reserve.md |
| adv-005 | 已覆盖 | 否 | 21 | 03-product-purchase-warehouse.md |
| adv-006 | 无答案（保持） | 是 | - | - |
| adv-007 | 已覆盖 | 否 | 31 | 03-ops-faq.md |
| adv-008 | 已覆盖 | 否 | 22,24,23 | 04-shipping-aftersale-rbac.md,05-exceptions.md,04-shipping-aftersale-rbac.md |
| adv-009 | 已覆盖 | 否 | 16,17,18 | 01-sales-order-state.md,01-sales-order-state.md,01-sales-order-state.md |
| adv-010 | 无答案（保持） | 是 | - | - |

## 待人工审核

全部 100 题标准答案仍为 AI 归纳 + 代码核对，不能直接当生产基准。优先复核：

- erp-001 至 erp-030：对照 ERP 状态机与库存事务
- ecom-*：确认模拟标记未被理解成真实平台政策
- adv-006 / adv-010：必须保持拒绝编造
- adv-007：现改为有答案，请确认 OCR 未实现这一事实仍成立
- adv-009：跨库题，当前标注偏 ERP 切片；电商侧 `02-exceptions-cs.md` chunk=28 亦含“不要把模拟跨境规则说成 ERP 功能”，评测时请同时选两个知识库
