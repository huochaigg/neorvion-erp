# V5 抽样评测结果

以下来自本地真实 probe / retrieval.test 接口，不是硬编码指标。

## erp-001 策略对照

### VECTOR

- 策略：VECTOR rerank_applied=False degraded=False
- 耗时：1105 ms
- stages：`{"ready_embeddings": 11, "vector_ms": 1097, "vector_ranks": [{"chunk_id": 16, "rank": 1, "similarity": 0.849298664969287}, {"chunk_id": 20, "rank": 2, "similarity": 0.7142643502793116}, {"chunk_id": 17, "rank": 3, "similarity": 0.7142467498779297}, {"chunk_id": 24, "rank": 4, "similarity": 0.6945158657143048}, {"chunk_id": 18, "rank": 5, "similarity": 0.6694799661636353}, {"chunk_id": 19, "rank": 6, "similarity": 0.6529686450958252}, {"chunk_id": 21, "rank": 7, "similarity": 0.6393258190556884}, {"chunk_id": 25, "rank": 8, "similarity": 0.628699779510498}, {"chunk_id": 9, "rank": 9, "similarity": 0.6270442453570118}, {"chunk_id": 22, "rank": 10, "similarity": 0.5456170602326712}, {"chunk_id": 23, "rank": 11, "similarity": 0.3732369395212034}]}`
- 召回：
- #1 chunk=16 01-sales-order-state.md vec=0.849298664969287 kw=None rrf=None rerank=None | # 销售订单状态机（已实现）  来源：`services/erp/app/models/sales_order.py`、`services/erp/app/services/sales_order.py`、`services/erp/app/services/sales_order_state.py`。以下描述当前代码
- #2 chunk=20 02-inventory-reserve.md vec=0.7142643502793116 kw=None rrf=None rerank=None | 销售预占流水用 `reference_type = SALES_ORDER` 区分来源订单。  ## 已实现规则  1. **销售确认**：写 `RESERVE`，增加 `reserved_quantity`，不减少 `quantity`。 2. **待出库取消**：写 `RELEASE`，减少 `reserved_q
- #3 chunk=17 01-sales-order-state.md vec=0.7142467498779297 kw=None rrf=None rerank=None | 确认只增加 `reserved_quantity`，**不扣减 `quantity`**。货还在仓库里，只是被这张订单占住。明细 `reserved_quantity` 写成购买数量。可用库存因此下降：可用 = `quantity - reserved_quantity`。  草稿直接确认无效。必须先提交到待确认。  
- #4 chunk=24 05-exceptions.md vec=0.6945158657143048 kw=None rrf=None rerank=None | # 业务异常与状态边界（已实现）  来源：销售、库存、出库、盘点服务中的错误码。以下异常会真实返回，不是文档设想。  ## 库存  - `INSUFFICIENT_RESERVED_INVENTORY`：释放或出库的预占数量超过 `reserved_quantity`。 - `STOCKTAKE_CONFLICT_WI
- #5 chunk=18 01-sales-order-state.md vec=0.6694799661636353 kw=None rrf=None rerank=None | 拣货本身不改变这些销售订单状态，也不扣库存；确认出库才扣减。详见出库文档。  ## 合法流转（已实现）  - `DRAFT` → `PENDING_CONFIRMATION` 或 `CANCELLED` - `PENDING_CONFIRMATION` → `WAITING_OUTBOUND` 或 `CANCELLED
- #6 chunk=19 02-inventory-reserve.md vec=0.6529686450958252 kw=None rrf=None rerank=None | # 库存预占、扣减与释放（已实现）  来源：`services/erp/app/models/inventory.py`、`services/erp/app/services/inventory.py`。库存维度是 **Tenant + Warehouse + SKU**，不是 SKU 单独一个数字，也不是落在 SPU
- #7 chunk=21 03-product-purchase-warehouse.md vec=0.6393258190556884 kw=None rrf=None rerank=None | # 商品、采购与仓库（已实现）  来源：商品 SPU/SKU 模型、采购单状态机、收货入库、仓库调拨、采购退货。优先描述代码已实现行为。  ## 商品  - SPU 是销售/管理单元，SKU 是库存与价格单元。 - 库存、预占、出库都落在 **SKU**，不落在 SPU。 - 同一租户内 SKU 编码唯一。**跨租户可
- #8 chunk=25 07-outbound-pick.md vec=0.628699779510498 kw=None rrf=None rerank=None | # 拣货、部分出库与确认出库（已实现）  来源：`services/erp/app/services/outbound.py`。模块约定：**拣货不扣库存；确认出库才同时减少 quantity 和 reserved。**  ## 确认订单后的出库单  销售订单确认成功后，同一事务生成第一张出库单（待拣货）。销售订单进入

### KEYWORD

- 策略：KEYWORD rerank_applied=False degraded=False
- 耗时：19 ms
- stages：`{"keyword_ms": 11, "keyword_ranks": [{"chunk_id": 16, "rank": 1, "score": 11.0}, {"chunk_id": 17, "rank": 2, "score": 8.0}, {"chunk_id": 21, "rank": 3, "score": 7.0}, {"chunk_id": 18, "rank": 4, "score": 7.0}, {"chunk_id": 22, "rank": 5, "score": 7.0}, {"chunk_id": 25, "rank": 6, "score": 6.0}, {"chunk_id": 24, "rank": 7, "score": 5.0}, {"chunk_id": 19, "rank": 8, "score": 4.0}, {"chunk_id": 20, "rank": 9, "score": 3.0}]}`
- 召回：
- #1 chunk=16 01-sales-order-state.md vec=None kw=11.0 rrf=None rerank=None | # 销售订单状态机（已实现）  来源：`services/erp/app/models/sales_order.py`、`services/erp/app/services/sales_order.py`、`services/erp/app/services/sales_order_state.py`。以下描述当前代码
- #2 chunk=17 01-sales-order-state.md vec=None kw=8.0 rrf=None rerank=None | 确认只增加 `reserved_quantity`，**不扣减 `quantity`**。货还在仓库里，只是被这张订单占住。明细 `reserved_quantity` 写成购买数量。可用库存因此下降：可用 = `quantity - reserved_quantity`。  草稿直接确认无效。必须先提交到待确认。  
- #3 chunk=21 03-product-purchase-warehouse.md vec=None kw=7.0 rrf=None rerank=None | # 商品、采购与仓库（已实现）  来源：商品 SPU/SKU 模型、采购单状态机、收货入库、仓库调拨、采购退货。优先描述代码已实现行为。  ## 商品  - SPU 是销售/管理单元，SKU 是库存与价格单元。 - 库存、预占、出库都落在 **SKU**，不落在 SPU。 - 同一租户内 SKU 编码唯一。**跨租户可
- #4 chunk=18 01-sales-order-state.md vec=None kw=7.0 rrf=None rerank=None | 拣货本身不改变这些销售订单状态，也不扣库存；确认出库才扣减。详见出库文档。  ## 合法流转（已实现）  - `DRAFT` → `PENDING_CONFIRMATION` 或 `CANCELLED` - `PENDING_CONFIRMATION` → `WAITING_OUTBOUND` 或 `CANCELLED
- #5 chunk=22 04-shipping-aftersale-rbac.md vec=None kw=7.0 rrf=None rerank=None | # 物流、售后、多租户与 RBAC（已实现）  来源：物流发货、售后、退款、`docs/rbac.md`、`docs/multi-tenancy.md`。身份权威在 ERP MySQL。Knowledge 不另建用户表。  ## 物流与签收  出库完成后才能创建物流单。部分交给承运商对应销售订单 `PARTIALLY_
- #6 chunk=25 07-outbound-pick.md vec=None kw=6.0 rrf=None rerank=None | # 拣货、部分出库与确认出库（已实现）  来源：`services/erp/app/services/outbound.py`。模块约定：**拣货不扣库存；确认出库才同时减少 quantity 和 reserved。**  ## 确认订单后的出库单  销售订单确认成功后，同一事务生成第一张出库单（待拣货）。销售订单进入
- #7 chunk=24 05-exceptions.md vec=None kw=5.0 rrf=None rerank=None | # 业务异常与状态边界（已实现）  来源：销售、库存、出库、盘点服务中的错误码。以下异常会真实返回，不是文档设想。  ## 库存  - `INSUFFICIENT_RESERVED_INVENTORY`：释放或出库的预占数量超过 `reserved_quantity`。 - `STOCKTAKE_CONFLICT_WI
- #8 chunk=19 02-inventory-reserve.md vec=None kw=4.0 rrf=None rerank=None | # 库存预占、扣减与释放（已实现）  来源：`services/erp/app/models/inventory.py`、`services/erp/app/services/inventory.py`。库存维度是 **Tenant + Warehouse + SKU**，不是 SKU 单独一个数字，也不是落在 SPU

### HYBRID

- 策略：HYBRID rerank_applied=False degraded=False
- 耗时：1028 ms
- stages：`{"ready_embeddings": 11, "vector_ms": 1007, "vector_ranks": [{"chunk_id": 16, "rank": 1, "similarity": 0.849298664969287}, {"chunk_id": 20, "rank": 2, "similarity": 0.7142643502793116}, {"chunk_id": 17, "rank": 3, "similarity": 0.7142467498779297}, {"chunk_id": 24, "rank": 4, "similarity": 0.6945158657143048}, {"chunk_id": 18, "rank": 5, "similarity": 0.6694799661636353}, {"chunk_id": 19, "rank": 6, "similarity": 0.6529686450958252}, {"chunk_id": 21, "rank": 7, "similarity": 0.6393258190556884}, {"chunk_id": 25, "rank": 8, "similarity": 0.628699779510498}, {"chunk_id": 9, "rank": 9, "similarity": 0.6270442453570118}, {"chunk_id": 22, "rank": 10, "similarity": 0.5456170602326712}, {"chunk_id": 23, "rank": 11, "similarity": 0.3732369395212034}], "keyword_ms": 13, "keyword_ranks": [{"chunk_id": 16, "rank": 1, "score": 11.0}, {"chunk_id": 17, "rank": 2, "score": 8.0}, {"chunk_id": 21, "rank": 3, "score": 7.0}, {"chunk_id": 18, "rank": 4, "score": 7.0}, {"chunk_id": 22, "rank": 5, "score": 7.0}, {"chunk_id": 25, "rank": 6, "score": 6.0}, {"chunk_id": 24, "rank": 7, "score": 5.0}, {"chunk_id": 19, "rank": 8, "score": 4.0}, {"chunk_id": 20, "rank": 9, "score": 3.0}], "rrf_ranks": [{"chunk_id": 16, "rrf": 0.03278688524590164}, {"chunk_id": 17, "rrf": 0.03200204813108039}, {"chunk_id": 18, "rrf": 0.031009615384615385}, {"chunk_id": 21, "rrf": 0.030798389007344232}, {"chunk_id": 20, "rrf": 0.030621785881252923}, {"chunk_id": 24, "rrf": 0.03055037313432836}, {"chunk_id": 19, "rrf": 0.029857397504456328}, {"chunk_id": 25, "rrf": 0.029857397504456328}, {"chunk_id": 22, "rrf": 0.02967032967032967}, {"chunk_id": 9, "rrf": 0.014492753623188406}, {"chunk_id": 23, "rrf": 0.014084507042253521}]}`
- 召回：
- #1 chunk=16 01-sales-order-state.md vec=0.849298664969287 kw=11.0 rrf=0.03278688524590164 rerank=None | # 销售订单状态机（已实现）  来源：`services/erp/app/models/sales_order.py`、`services/erp/app/services/sales_order.py`、`services/erp/app/services/sales_order_state.py`。以下描述当前代码
- #2 chunk=17 01-sales-order-state.md vec=0.7142467498779297 kw=8.0 rrf=0.03200204813108039 rerank=None | 确认只增加 `reserved_quantity`，**不扣减 `quantity`**。货还在仓库里，只是被这张订单占住。明细 `reserved_quantity` 写成购买数量。可用库存因此下降：可用 = `quantity - reserved_quantity`。  草稿直接确认无效。必须先提交到待确认。  
- #3 chunk=18 01-sales-order-state.md vec=0.6694799661636353 kw=7.0 rrf=0.031009615384615385 rerank=None | 拣货本身不改变这些销售订单状态，也不扣库存；确认出库才扣减。详见出库文档。  ## 合法流转（已实现）  - `DRAFT` → `PENDING_CONFIRMATION` 或 `CANCELLED` - `PENDING_CONFIRMATION` → `WAITING_OUTBOUND` 或 `CANCELLED
- #4 chunk=21 03-product-purchase-warehouse.md vec=0.6393258190556884 kw=7.0 rrf=0.030798389007344232 rerank=None | # 商品、采购与仓库（已实现）  来源：商品 SPU/SKU 模型、采购单状态机、收货入库、仓库调拨、采购退货。优先描述代码已实现行为。  ## 商品  - SPU 是销售/管理单元，SKU 是库存与价格单元。 - 库存、预占、出库都落在 **SKU**，不落在 SPU。 - 同一租户内 SKU 编码唯一。**跨租户可
- #5 chunk=20 02-inventory-reserve.md vec=0.7142643502793116 kw=3.0 rrf=0.030621785881252923 rerank=None | 销售预占流水用 `reference_type = SALES_ORDER` 区分来源订单。  ## 已实现规则  1. **销售确认**：写 `RESERVE`，增加 `reserved_quantity`，不减少 `quantity`。 2. **待出库取消**：写 `RELEASE`，减少 `reserved_q
- #6 chunk=24 05-exceptions.md vec=0.6945158657143048 kw=5.0 rrf=0.03055037313432836 rerank=None | # 业务异常与状态边界（已实现）  来源：销售、库存、出库、盘点服务中的错误码。以下异常会真实返回，不是文档设想。  ## 库存  - `INSUFFICIENT_RESERVED_INVENTORY`：释放或出库的预占数量超过 `reserved_quantity`。 - `STOCKTAKE_CONFLICT_WI
- #7 chunk=19 02-inventory-reserve.md vec=0.6529686450958252 kw=4.0 rrf=0.029857397504456328 rerank=None | # 库存预占、扣减与释放（已实现）  来源：`services/erp/app/models/inventory.py`、`services/erp/app/services/inventory.py`。库存维度是 **Tenant + Warehouse + SKU**，不是 SKU 单独一个数字，也不是落在 SPU
- #8 chunk=25 07-outbound-pick.md vec=0.628699779510498 kw=6.0 rrf=0.029857397504456328 rerank=None | # 拣货、部分出库与确认出库（已实现）  来源：`services/erp/app/services/outbound.py`。模块约定：**拣货不扣库存；确认出库才同时减少 quantity 和 reserved。**  ## 确认订单后的出库单  销售订单确认成功后，同一事务生成第一张出库单（待拣货）。销售订单进入

### HYBRID_rerank

- 策略：HYBRID rerank_applied=True degraded=False
- 耗时：2247 ms
- stages：`{"ready_embeddings": 11, "vector_ms": 1110, "vector_ranks": [{"chunk_id": 16, "rank": 1, "similarity": 0.849298664969287}, {"chunk_id": 20, "rank": 2, "similarity": 0.7142643502793116}, {"chunk_id": 17, "rank": 3, "similarity": 0.7142467498779297}, {"chunk_id": 24, "rank": 4, "similarity": 0.6945158657143048}, {"chunk_id": 18, "rank": 5, "similarity": 0.6694799661636353}, {"chunk_id": 19, "rank": 6, "similarity": 0.6529686450958252}, {"chunk_id": 21, "rank": 7, "similarity": 0.6393258190556884}, {"chunk_id": 25, "rank": 8, "similarity": 0.628699779510498}, {"chunk_id": 9, "rank": 9, "similarity": 0.6270442453570118}, {"chunk_id": 22, "rank": 10, "similarity": 0.5456170602326712}, {"chunk_id": 23, "rank": 11, "similarity": 0.3732369395212034}], "keyword_ms": 8, "keyword_ranks": [{"chunk_id": 16, "rank": 1, "score": 11.0}, {"chunk_id": 17, "rank": 2, "score": 8.0}, {"chunk_id": 21, "rank": 3, "score": 7.0}, {"chunk_id": 18, "rank": 4, "score": 7.0}, {"chunk_id": 22, "rank": 5, "score": 7.0}, {"chunk_id": 25, "rank": 6, "score": 6.0}, {"chunk_id": 24, "rank": 7, "score": 5.0}, {"chunk_id": 19, "rank": 8, "score": 4.0}, {"chunk_id": 20, "rank": 9, "score": 3.0}], "rrf_ranks": [{"chunk_id": 16, "rrf": 0.03278688524590164}, {"chunk_id": 17, "rrf": 0.03200204813108039}, {"chunk_id": 18, "rrf": 0.031009615384615385}, {"chunk_id": 21, "rrf": 0.030798389007344232}, {"chunk_id": 20, "rrf": 0.030621785881252923}, {"chunk_id": 24, "rrf": 0.03055037313432836}, {"chunk_id": 19, "rrf": 0.029857397504456328}, {"chunk_id": 25, "rrf": 0.029857397504456328}, {"chunk_id": 22, "rrf": 0.02967032967032967}, {"chunk_id": 9, "rrf": 0.014492753623188406}, {"chunk_id": 23, "rrf": 0.014084507042253521}], "rerank_ms": 1120, "rerank_applied": true, "rerank_degraded": false}`
- 召回：
- #1 chunk=16 01-sales-order-state.md vec=0.849298664969287 kw=11.0 rrf=0.03278688524590164 rerank=0.985890866059624 | # 销售订单状态机（已实现）  来源：`services/erp/app/models/sales_order.py`、`services/erp/app/services/sales_order.py`、`services/erp/app/services/sales_order_state.py`。以下描述当前代码
- #2 chunk=17 01-sales-order-state.md vec=0.7142467498779297 kw=8.0 rrf=0.03200204813108039 rerank=0.9028391255860231 | 确认只增加 `reserved_quantity`，**不扣减 `quantity`**。货还在仓库里，只是被这张订单占住。明细 `reserved_quantity` 写成购买数量。可用库存因此下降：可用 = `quantity - reserved_quantity`。  草稿直接确认无效。必须先提交到待确认。  
- #3 chunk=18 01-sales-order-state.md vec=0.6694799661636353 kw=7.0 rrf=0.031009615384615385 rerank=0.8391153913429354 | 拣货本身不改变这些销售订单状态，也不扣库存；确认出库才扣减。详见出库文档。  ## 合法流转（已实现）  - `DRAFT` → `PENDING_CONFIRMATION` 或 `CANCELLED` - `PENDING_CONFIRMATION` → `WAITING_OUTBOUND` 或 `CANCELLED
- #4 chunk=21 03-product-purchase-warehouse.md vec=0.6393258190556884 kw=7.0 rrf=0.030798389007344232 rerank=0.8026144755438314 | # 商品、采购与仓库（已实现）  来源：商品 SPU/SKU 模型、采购单状态机、收货入库、仓库调拨、采购退货。优先描述代码已实现行为。  ## 商品  - SPU 是销售/管理单元，SKU 是库存与价格单元。 - 库存、预占、出库都落在 **SKU**，不落在 SPU。 - 同一租户内 SKU 编码唯一。**跨租户可
- #5 chunk=24 05-exceptions.md vec=0.6945158657143048 kw=5.0 rrf=0.03055037313432836 rerank=0.6932295181032802 | # 业务异常与状态边界（已实现）  来源：销售、库存、出库、盘点服务中的错误码。以下异常会真实返回，不是文档设想。  ## 库存  - `INSUFFICIENT_RESERVED_INVENTORY`：释放或出库的预占数量超过 `reserved_quantity`。 - `STOCKTAKE_CONFLICT_WI
- #6 chunk=9 06-parse-sample.pdf vec=0.6270442453570118 kw=None rrf=0.014492753623188406 rerank=0.6753687132366512 | Neorvion ERP: confirming a sales order writes RESERVE and increases reserved_quantity. It does not deduct quantity. Quantity decreases only on OUTBOUND.
- #7 chunk=20 02-inventory-reserve.md vec=0.7142643502793116 kw=3.0 rrf=0.030621785881252923 rerank=0.6584663696319983 | 销售预占流水用 `reference_type = SALES_ORDER` 区分来源订单。  ## 已实现规则  1. **销售确认**：写 `RESERVE`，增加 `reserved_quantity`，不减少 `quantity`。 2. **待出库取消**：写 `RELEASE`，减少 `reserved_q
- #8 chunk=19 02-inventory-reserve.md vec=0.6529686450958252 kw=4.0 rrf=0.029857397504456328 rerank=0.619492779602622 | # 库存预占、扣减与释放（已实现）  来源：`services/erp/app/models/inventory.py`、`services/erp/app/services/inventory.py`。库存维度是 **Tenant + Warehouse + SKU**，不是 SKU 单独一个数字，也不是落在 SPU

## erp-001 / case 1

- 问题：销售订单 DRAFT 状态会不会预占库存？
- 策略：HYBRID  rerank_applied=True degraded=False
- 耗时：2255 ms
- stages：`{"ready_embeddings": 11, "vector_ms": 1133, "vector_ranks": [{"chunk_id": 16, "rank": 1, "similarity": 0.849298664969287}, {"chunk_id": 20, "rank": 2, "similarity": 0.7142643502793116}, {"chunk_id": 17, "rank": 3, "similarity": 0.7142467498779297}, {"chunk_id": 24, "rank": 4, "similarity": 0.6945158657143048}, {"chunk_id": 18, "rank": 5, "similarity": 0.6694799661636353}, {"chunk_id": 19, "rank": 6, "similarity": 0.6529686450958252}, {"chunk_id": 21, "rank": 7, "similarity": 0.6393258190556884}, {"chunk_id": 25, "rank": 8, "similarity": 0.628699779510498}, {"chunk_id": 9, "rank": 9, "similarity": 0.6270442453570118}, {"chunk_id": 22, "rank": 10, "similarity": 0.5456170602326712}, {"chunk_id": 23, "rank": 11, "similarity": 0.3732369395212034}], "keyword_ms": 21, "keyword_ranks": [{"chunk_id": 16, "rank": 1, "score": 11.0}, {"chunk_id": 17, "rank": 2, "score": 8.0}, {"chunk_id": 21, "rank": 3, "score": 7.0}, {"chunk_id": 18, "rank": 4, "score": 7.0}, {"chunk_id": 22, "rank": 5, "score": 7.0}, {"chunk_id": 25, "rank": 6, "score": 6.0}, {"chunk_id": 24, "rank": 7, "score": 5.0}, {"chunk_id": 19, "rank": 8, "score": 4.0}, {"chunk_id": 20, "rank": 9, "score": 3.0}], "rrf_ranks": [{"chunk_id": 16, "rrf": 0.03278688524590164}, {"chunk_id": 17, "rrf": 0.03200204813108039}, {"chunk_id": 18, "rrf": 0.031009615384615385}, {"chunk_id": 21, "rrf": 0.030798389007344232}, {"chunk_id": 20, "rrf": 0.030621785881252923}, {"chunk_id": 24, "rrf": 0.03055037313432836}, {"chunk_id": 19, "rrf": 0.029857397504456328}, {"chunk_id": 25, "rrf": 0.029857397504456328}, {"chunk_id": 22, "rrf": 0.02967032967032967}, {"chunk_id": 9, "rrf": 0.014492753623188406}, {"chunk_id": 23, "rrf": 0.014084507042253521}], "rerank_ms": 1094, "rerank_applied": true, "rerank_degraded": false}`
- retrieval_metrics：`{"metric_version": "v4-chunk-ndcg-exp", "granularity": "chunk", "k": 8, "relevant_count": 3, "retrieved_count": 8, "hit_rate": 1.0, "recall": 1.0, "precision": 0.375, "mrr": 1.0, "ndcg": 1.0, "context_precision": 0.375, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 0.3333333333333333, "precision@1": 1.0, "ndcg@1": 1.0, "hit_rate@3": 1.0, "recall@3": 1.0, "precision@3": 1.0, "ndcg@3": 1.0, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.6, "ndcg@5": 1.0, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.3, "ndcg@10": 1.0, "document": {"metric_version": "v4-chunk-ndcg-exp", "granularity": "document", "k": 8, "relevant_count": 1, "retrieved_count": 5, "hit_rate": 1.0, "recall": 1.0, "precision": 0.125, "mrr": 1.0, "ndcg": 1.0, "context_precision": 0.2, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 1.0, "precision@1": 1.0, "ndcg@1": 1.0, "hit_rate@3": 1.0, "recall@3": 1.0, "precision@3": 0.3333333333333333, "ndcg@3": 1.0, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.2, "ndcg@5": 1.0, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.1, "ndcg@10": 1.0}}`
- citations：`[{"chunk_id": 16, "document_id": 2, "filename": "01-sales-order-state.md", "final_rank": 1}, {"chunk_id": 17, "document_id": 2, "filename": "01-sales-order-state.md", "final_rank": 2}, {"chunk_id": 18, "document_id": 2, "filename": "01-sales-order-state.md", "final_rank": 3}, {"chunk_id": 21, "document_id": 4, "filename": "03-product-purchase-warehouse.md", "final_rank": 4}, {"chunk_id": 24, "document_id": 6, "filename": "05-exceptions.md", "final_rank": 5}, {"chunk_id": 9, "document_id": 7, "filename": "06-parse-sample.pdf", "final_rank": 6}, {"chunk_id": 20, "document_id": 3, "filename": "02-inventory-reserve.md", "final_rank": 7}, {"chunk_id": 19, "document_id": 3, "filename": "02-inventory-reserve.md", "final_rank": 8}]`
- usage：`{"prompt_tokens": 2920, "completion_tokens": 202}`（首次 generate=1）
- 模型回答：不会。销售订单处于 **DRAFT（草稿）状态时不预占库存**。依据 [1]：DRAFT 不会预占库存；提交仍不预占；确认才 RESERVE。引用 `01-sales-order-state.md` chunk=16。

召回 Chunk：
- #1 chunk=16 01-sales-order-state.md vec=0.849298664969287 kw=11.0
- #2 chunk=17 01-sales-order-state.md vec=0.7142467498779297 kw=8.0
- #3 chunk=18 01-sales-order-state.md vec=0.6694799661636353 kw=7.0
- #4 chunk=21 03-product-purchase-warehouse.md vec=0.6393258190556884 kw=7.0
- #5 chunk=24 05-exceptions.md vec=0.6945158657143048 kw=5.0
- #6 chunk=9 06-parse-sample.pdf vec=0.6270442453570118 kw=None
- #7 chunk=20 02-inventory-reserve.md vec=0.7142643502793116 kw=3.0
- #8 chunk=19 02-inventory-reserve.md vec=0.6529686450958252 kw=4.0

## erp-010 / case 10

- 问题：待确认订单确认成功后进入什么状态？
- 策略：HYBRID  rerank_applied=True degraded=False
- 耗时：2181 ms
- stages：`{"ready_embeddings": 11, "vector_ms": 1088, "vector_ranks": [{"chunk_id": 16, "rank": 1, "similarity": 0.6910713683281697}, {"chunk_id": 18, "rank": 2, "similarity": 0.6816555451360032}, {"chunk_id": 17, "rank": 3, "similarity": 0.6130240194187163}, {"chunk_id": 24, "rank": 4, "similarity": 0.5948147773742718}, {"chunk_id": 25, "rank": 5, "similarity": 0.5795902860408861}, {"chunk_id": 20, "rank": 6, "similarity": 0.5758736639173432}, {"chunk_id": 21, "rank": 7, "similarity": 0.5631834193249441}, {"chunk_id": 9, "rank": 8, "similarity": 0.5273692856962775}, {"chunk_id": 22, "rank": 9, "similarity": 0.4858159874136472}, {"chunk_id": 19, "rank": 10, "similarity": 0.45428899203008544}, {"chunk_id": 23, "rank": 11, "similarity": 0.34462711013070824}], "keyword_ms": 15, "keyword_ranks": [{"chunk_id": 25, "rank": 1, "score": 10.0}, {"chunk_id": 16, "rank": 2, "score": 6.0}, {"chunk_id": 24, "rank": 3, "score": 5.0}, {"chunk_id": 21, "rank": 4, "score": 4.0}, {"chunk_id": 22, "rank": 5, "score": 4.0}, {"chunk_id": 17, "rank": 6, "score": 4.0}, {"chunk_id": 18, "rank": 7, "score": 3.0}, {"chunk_id": 20, "rank": 8, "score": 2.0}, {"chunk_id": 19, "rank": 9, "score": 1.0}], "rrf_ranks": [{"chunk_id": 16, "rrf": 0.03252247488101534}, {"chunk_id": 25, "rrf": 0.03177805800756621}, {"chunk_id": 24, "rrf": 0.03149801587301587}, {"chunk_id": 18, "rrf": 0.031054405392392875}, {"chunk_id": 17, "rrf": 0.031024531024531024}, {"chunk_id": 21, "rrf": 0.03055037313432836}, {"chunk_id": 22, "rrf": 0.029877369007803793}, {"chunk_id": 20, "rrf": 0.029857397504456328}, {"chunk_id": 19, "rrf": 0.02877846790890269}, {"chunk_id": 9, "rrf": 0.014705882352941176}, {"chunk_id": 23, "rrf": 0.014084507042253521}], "rerank_ms": 1061, "rerank_applied": true, "rerank_degraded": false}`
- retrieval_metrics：`{"metric_version": "v4-chunk-ndcg-exp", "granularity": "chunk", "k": 8, "relevant_count": 3, "retrieved_count": 8, "hit_rate": 1.0, "recall": 1.0, "precision": 0.375, "mrr": 1.0, "ndcg": 0.8529278650606568, "context_precision": 0.375, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 0.3333333333333333, "precision@1": 1.0, "ndcg@1": 1.0, "hit_rate@3": 1.0, "recall@3": 0.3333333333333333, "precision@3": 0.3333333333333333, "ndcg@3": 0.4692787260227565, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.6, "ndcg@5": 0.8529278650606568, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.3, "ndcg@10": 0.8529278650606568, "document": {"metric_version": "v4-chunk-ndcg-exp", "granularity": "document", "k": 8, "relevant_count": 1, "retrieved_count": 6, "hit_rate": 1.0, "recall": 1.0, "precision": 0.125, "mrr": 1.0, "ndcg": 1.0, "context_precision": 0.16666666666666666, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 1.0, "precision@1": 1.0, "ndcg@1": 1.0, "hit_rate@3": 1.0, "recall@3": 1.0, "precision@3": 0.3333333333333333, "ndcg@3": 1.0, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.2, "ndcg@5": 1.0, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.1, "ndcg@10": 1.0}}`
- citations：`[{"chunk_id": 16, "document_id": 2, "filename": "01-sales-order-state.md", "final_rank": 1}, {"chunk_id": 25, "document_id": 14, "filename": "07-outbound-pick.md", "final_rank": 2}, {"chunk_id": 24, "document_id": 6, "filename": "05-exceptions.md", "final_rank": 3}, {"chunk_id": 18, "document_id": 2, "filename": "01-sales-order-state.md", "final_rank": 4}, {"chunk_id": 17, "document_id": 2, "filename": "01-sales-order-state.md", "final_rank": 5}, {"chunk_id": 22, "document_id": 5, "filename": "04-shipping-aftersale-rbac.md", "final_rank": 6}, {"chunk_id": 9, "document_id": 7, "filename": "06-parse-sample.pdf", "final_rank": 7}, {"chunk_id": 20, "document_id": 3, "filename": "02-inventory-reserve.md", "final_rank": 8}]`
- usage：`{"prompt_tokens": 2984, "completion_tokens": 96}`（首次 generate=1）
- 模型回答：待确认订单（`PENDING_CONFIRMATION`）确认成功后进入 **`WAITING_OUTBOUND`**（待出库）状态 [1][4]。

召回 Chunk：
- #1 chunk=16 01-sales-order-state.md vec=0.6910713683281697 kw=6.0
- #2 chunk=25 07-outbound-pick.md vec=0.5795902860408861 kw=10.0
- #3 chunk=24 05-exceptions.md vec=0.5948147773742718 kw=5.0
- #4 chunk=18 01-sales-order-state.md vec=0.6816555451360032 kw=3.0
- #5 chunk=17 01-sales-order-state.md vec=0.6130240194187163 kw=4.0
- #6 chunk=22 04-shipping-aftersale-rbac.md vec=0.4858159874136472 kw=4.0
- #7 chunk=9 06-parse-sample.pdf vec=0.5273692856962775 kw=None
- #8 chunk=20 02-inventory-reserve.md vec=0.5758736639173432 kw=2.0

## ecom-008 / case 38

- 问题：模拟物流把头程和尾程分别定义成什么？
- 策略：HYBRID  rerank_applied=True degraded=False
- 耗时：2566 ms
- stages：`{"ready_embeddings": 3, "vector_ms": 1432, "vector_ranks": [{"chunk_id": 26, "rank": 1, "similarity": 0.6570832729339646}, {"chunk_id": 27, "rank": 2, "similarity": 0.5480454506819903}, {"chunk_id": 28, "rank": 3, "similarity": 0.5470192106354717}], "keyword_ms": 10, "keyword_ranks": [{"chunk_id": 26, "rank": 1, "score": 5.0}, {"chunk_id": 27, "rank": 2, "score": 3.0}, {"chunk_id": 28, "rank": 3, "score": 1.0}], "rrf_ranks": [{"chunk_id": 26, "rrf": 0.03278688524590164}, {"chunk_id": 27, "rrf": 0.03225806451612903}, {"chunk_id": 28, "rrf": 0.031746031746031744}], "rerank_ms": 1107, "rerank_applied": true, "rerank_degraded": false}`
- retrieval_metrics：`{"metric_version": "v4-chunk-ndcg-exp", "granularity": "chunk", "k": 8, "relevant_count": 2, "retrieved_count": 3, "hit_rate": 1.0, "recall": 1.0, "precision": 0.25, "mrr": 1.0, "ndcg": 1.0, "context_precision": 0.6666666666666666, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 0.5, "precision@1": 1.0, "ndcg@1": 1.0, "hit_rate@3": 1.0, "recall@3": 1.0, "precision@3": 0.6666666666666666, "ndcg@3": 1.0, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.4, "ndcg@5": 1.0, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.2, "ndcg@10": 1.0, "document": {"metric_version": "v4-chunk-ndcg-exp", "granularity": "document", "k": 8, "relevant_count": 1, "retrieved_count": 2, "hit_rate": 1.0, "recall": 1.0, "precision": 0.125, "mrr": 1.0, "ndcg": 1.0, "context_precision": 0.5, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 1.0, "precision@1": 1.0, "ndcg@1": 1.0, "hit_rate@3": 1.0, "recall@3": 1.0, "precision@3": 0.3333333333333333, "ndcg@3": 1.0, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.2, "ndcg@5": 1.0, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.1, "ndcg@10": 1.0}}`
- citations：`[{"chunk_id": 26, "document_id": 8, "filename": "01-cross-border-ops.md", "final_rank": 1}, {"chunk_id": 27, "document_id": 8, "filename": "01-cross-border-ops.md", "final_rank": 2}, {"chunk_id": 28, "document_id": 9, "filename": "02-exceptions-cs.md", "final_rank": 3}]`
- usage：`{"prompt_tokens": 1204, "completion_tokens": 53}`（首次 generate=1）
- 模型回答：**头程**：工厂/国内仓 → 海外仓（在途不可售）。**尾程**：海外仓 → 消费者。[1]

召回 Chunk：
- #1 chunk=26 01-cross-border-ops.md vec=0.6570832729339646 kw=5.0
- #2 chunk=27 01-cross-border-ops.md vec=0.5480454506819903 kw=3.0
- #3 chunk=28 02-exceptions-cs.md vec=0.5470192106354717 kw=1.0

## gen-007 / case 67

- 问题：Knowledge 的关键词检索是 BM25 吗？
- 策略：HYBRID  rerank_applied=True degraded=False
- 耗时：2159 ms
- stages：`{"ready_embeddings": 4, "vector_ms": 1074, "vector_ranks": [{"chunk_id": 31, "rank": 1, "similarity": 0.6753790765548853}, {"chunk_id": 30, "rank": 2, "similarity": 0.607018589973454}, {"chunk_id": 32, "rank": 3, "similarity": 0.58458893482817}, {"chunk_id": 29, "rank": 4, "similarity": 0.3939097117347048}], "keyword_ms": 7, "keyword_ranks": [{"chunk_id": 30, "rank": 1, "score": 3.0}, {"chunk_id": 29, "rank": 2, "score": 2.0}, {"chunk_id": 31, "rank": 3, "score": 2.0}, {"chunk_id": 32, "rank": 4, "score": 1.0}], "rrf_ranks": [{"chunk_id": 30, "rrf": 0.03252247488101534}, {"chunk_id": 31, "rrf": 0.032266458495966696}, {"chunk_id": 29, "rrf": 0.031754032258064516}, {"chunk_id": 32, "rrf": 0.03149801587301587}], "rerank_ms": 1071, "rerank_applied": true, "rerank_degraded": false}`
- retrieval_metrics：`{"metric_version": "v4-chunk-ndcg-exp", "granularity": "chunk", "k": 8, "relevant_count": 1, "retrieved_count": 4, "hit_rate": 1.0, "recall": 1.0, "precision": 0.125, "mrr": 1.0, "ndcg": 1.0, "context_precision": 0.25, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 1.0, "precision@1": 1.0, "ndcg@1": 1.0, "hit_rate@3": 1.0, "recall@3": 1.0, "precision@3": 0.3333333333333333, "ndcg@3": 1.0, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.2, "ndcg@5": 1.0, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.1, "ndcg@10": 1.0, "document": {"metric_version": "v4-chunk-ndcg-exp", "granularity": "document", "k": 8, "relevant_count": 1, "retrieved_count": 4, "hit_rate": 1.0, "recall": 1.0, "precision": 0.125, "mrr": 1.0, "ndcg": 1.0, "context_precision": 0.25, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 1.0, "precision@1": 1.0, "ndcg@1": 1.0, "hit_rate@3": 1.0, "recall@3": 1.0, "precision@3": 0.3333333333333333, "ndcg@3": 1.0, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.2, "ndcg@5": 1.0, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.1, "ndcg@10": 1.0}}`
- citations：`[{"chunk_id": 30, "document_id": 11, "filename": "02-postgres-redis.md", "final_rank": 1}, {"chunk_id": 31, "document_id": 12, "filename": "03-ops-faq.md", "final_rank": 2}, {"chunk_id": 29, "document_id": 10, "filename": "01-python-fastapi.md", "final_rank": 3}, {"chunk_id": 32, "document_id": 13, "filename": "04-troubleshooting.md", "final_rank": 4}]`
- usage：`{"prompt_tokens": 1529, "completion_tokens": 102}`（首次 generate=1）
- 模型回答：不是 BM25。KEYWORD 使用 simple FTS + trigram + 中文片段 ILIKE [1][2]。

召回 Chunk：
- #1 chunk=30 02-postgres-redis.md vec=0.607018589973454 kw=3.0
- #2 chunk=31 03-ops-faq.md vec=0.6753790765548853 kw=2.0
- #3 chunk=29 01-python-fastapi.md vec=0.3939097117347048 kw=2.0
- #4 chunk=32 04-troubleshooting.md vec=0.58458893482817 kw=1.0
