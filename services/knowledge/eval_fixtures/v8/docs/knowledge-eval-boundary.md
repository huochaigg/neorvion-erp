# 评测不改索引

来源：`services/knowledge/app/services/evaluation.py` 模块说明，以及 `metrics.py`。

评测不修改线上 Chunk 或向量索引。Hit、Recall、Precision、MRR、nDCG 由代码计算，禁止用 LLM 给这些指标打分。

无答案题的 `false_recall` 只表示 Top-K 非空，定义标记为 `top_k_nonempty_not_hallucination_rate`。它不是幻觉率。

LLM Judge 只产生主观的 Faithfulness、Answer Relevancy、Answer Correctness。Judge 失败时不得伪造分数。
