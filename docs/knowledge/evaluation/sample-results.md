# V5 抽样评测结果

以下来自本地真实 probe 接口，不是硬编码指标。

## erp-002 / case 2

- 问题：确认销售订单时扣减的是 quantity 还是只做预占？
- 策略：HYBRID  rerank_applied=True degraded=False
- 耗时：1442 ms
- stages：`{"vector_ms": 626, "vector_ranks": [], "keyword_ms": 4, "keyword_ranks": [{"chunk_id": 5, "rank": 1, "score": 1.0}, {"chunk_id": 8, "rank": 2, "score": 0.5}, {"chunk_id": 4, "rank": 3, "score": 0.3}, {"chunk_id": 9, "rank": 4, "score": 0.3}, {"chunk_id": 6, "rank": 5, "score": 0.1}], "rrf_ranks": [{"chunk_id": 5, "rrf": 0.01639344262295082}, {"chunk_id": 8, "rrf": 0.016129032258064516}, {"chunk_id": 4, "rrf": 0.015873015873015872}, {"chunk_id": 9, "rrf": 0.015625}, {"chunk_id": 6, "rrf": 0.015384615384615385}], "rerank_ms": 807, "rerank_applied": true, "rerank_degraded": false}`
- retrieval_metrics：`{"metric_version": "v4-chunk-ndcg-exp", "granularity": "chunk", "k": 8, "relevant_count": 3, "retrieved_count": 5, "hit_rate": 1.0, "recall": 0.6666666666666666, "precision": 0.25, "mrr": 1.0, "ndcg": 0.6254336383564085, "context_precision": 0.4, "context_recall": 0.6666666666666666, "hit_rate@1": 1.0, "recall@1": 0.3333333333333333, "precision@1": 1.0, "ndcg@1": 0.42857142857142855, "hit_rate@3": 1.0, "recall@3": 0.6666666666666666, "precision@3": 0.6666666666666666, "ndcg@3": 0.6254336383564085, "hit_rate@5": 1.0, "recall@5": 0.6666666666666666, "precision@5": 0.4, "ndcg@5": 0.6254336383564085, "hit_rate@10": 1.0, "recall@10": 0.6666666666666666, "precision@10": 0.2, "ndcg@10": 0.6254336383564085, "document": {"metric_version": "v4-chunk-ndcg-exp", "granularity": "document", "k": 8, "relevant_count": 2, "retrieved_count": 5, "hit_rate": 1.0, "recall": 1.0, "precision": 0.25, "mrr": 1.0, "ndcg": 0.7309292742059024, "context_precision": 0.4, "context_recall": 1.0, "hit_rate@1": 1.0, "recall@1": 0.5, "precision@1": 1.0, "ndcg@1": 0.42857142857142855, "hit_rate@3": 1.0, "recall@3": 1.0, "precision@3": 0.6666666666666666, "ndcg@3": 0.7309292742059024, "hit_rate@5": 1.0, "recall@5": 1.0, "precision@5": 0.4, "ndcg@5": 0.7309292742059024, "hit_rate@10": 1.0, "recall@10": 1.0, "precision@10": 0.2, "ndcg@10": 0.7309292742059024}}`
- usage：`null`

召回 Chunk：
- #1 chunk=4 01-sales-order-state.md vec=None kw=0.3
- #2 chunk=9 06-parse-sample.pdf vec=None kw=0.3
- #3 chunk=5 02-inventory-reserve.md vec=None kw=1.0
- #4 chunk=8 05-exceptions.md vec=None kw=0.5
- #5 chunk=6 03-product-purchase-warehouse.md vec=None kw=0.1

## ecom-008 / case 38

- 问题：模拟物流把头程和尾程分别定义成什么？
- 策略：HYBRID  rerank_applied=False degraded=False
- 耗时：624 ms
- stages：`{"vector_ms": 615, "vector_ranks": [], "keyword_ms": 3, "keyword_ranks": [], "rrf_ranks": []}`
- retrieval_metrics：`{"metric_version": "v4-chunk-ndcg-exp", "granularity": "chunk", "k": 8, "relevant_count": 1, "retrieved_count": 0, "hit_rate": 0.0, "recall": 0.0, "precision": 0.0, "mrr": 0.0, "ndcg": 0.0, "context_precision": 0.0, "context_recall": 0.0, "hit_rate@1": 0.0, "recall@1": 0.0, "precision@1": 0.0, "ndcg@1": 0.0, "hit_rate@3": 0.0, "recall@3": 0.0, "precision@3": 0.0, "ndcg@3": 0.0, "hit_rate@5": 0.0, "recall@5": 0.0, "precision@5": 0.0, "ndcg@5": 0.0, "hit_rate@10": 0.0, "recall@10": 0.0, "precision@10": 0.0, "ndcg@10": 0.0, "document": {"metric_version": "v4-chunk-ndcg-exp", "granularity": "document", "k": 8, "relevant_count": 1, "retrieved_count": 0, "hit_rate": 0.0, "recall": 0.0, "precision": 0.0, "mrr": 0.0, "ndcg": 0.0, "context_precision": 0.0, "context_recall": 0.0, "hit_rate@1": 0.0, "recall@1": 0.0, "precision@1": 0.0, "ndcg@1": 0.0, "hit_rate@3": 0.0, "recall@3": 0.0, "precision@3": 0.0, "ndcg@3": 0.0, "hit_rate@5": 0.0, "recall@5": 0.0, "precision@5": 0.0, "ndcg@5": 0.0, "hit_rate@10": 0.0, "recall@10": 0.0, "precision@10": 0.0, "ndcg@10": 0.0}}`
- usage：`null`

召回 Chunk：

## adv-006 / case 96

- 问题：Amazon 欧洲站当前的佣金百分比是多少？请根据本知识库作答。
- 策略：HYBRID  rerank_applied=False degraded=False
- 耗时：627 ms
- stages：`{"vector_ms": 619, "vector_ranks": [], "keyword_ms": 2, "keyword_ranks": [], "rrf_ranks": []}`
- retrieval_metrics：`{"metric_version": "v4-chunk-ndcg-exp", "granularity": "chunk", "unanswerable": true, "false_recall": 0.0, "empty_ok": 1.0, "retrieved_count": 0}`
- usage：`null`

召回 Chunk：
