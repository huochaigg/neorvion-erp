"""V8 诊断题包。只描述可追溯语料和题目，不在导入或启动时写数据库。

V8-00-Baseline 指向已有评测集，本目录不复制、不覆盖那 100 题。
有答案题的证据是文档中的原句，不是 Chunk ID。导入后必须人工标注，不能直接 READY。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "eval_fixtures" / "v8"
DATASETS = (
    "V8-01-Hard-Cases",
    "V8-02-Multi-Doc",
    "V8-03-Unanswerable",
    "V8-04-Hallucination",
    "V8-05-Long-Query",
    "V8-06-Retrieval-Precision",
    "V8-07-Regression",
)
EXPERIMENT_PRESETS = (
    {"name": "V8-A-VECTOR", "strategy": "VECTOR", "rerank": False},
    {"name": "V8-B-KEYWORD", "strategy": "KEYWORD", "rerank": False},
    {"name": "V8-C-HYBRID", "strategy": "HYBRID", "rerank": False},
    {"name": "V8-D-HYBRID-RERANK", "strategy": "HYBRID", "rerank": True},
)

_DOCS: list[dict] = [
    {
        "filename": "sales-order-status.md",
        "source_type": "DERIVED",
        "domain": "sales-order",
        "scenario": "state-machine",
        "datasets": ["V8-01-Hard-Cases", "V8-07-Regression"],
        "source_paths": ["services/erp/app/models/sales_order.py"],
        "body": """# 销售订单状态

来源：`services/erp/app/models/sales_order.py` 的 `SalesOrderStatus`。本文只转写代码注释中的状态含义，不是新的业务规则。

## 状态

| 状态 | 代码注释中的含义 |
| --- | --- |
| DRAFT | 草稿。可改客户、仓库、收货信息和明细；可提交或取消。未预占库存。 |
| PENDING_CONFIRMATION | 待确认。已提交、等待审核。确认才会预占库存；也可取消且不动库存。 |
| WAITING_OUTBOUND | 待出库。已确认并预占。尚未正式出库时可以整单取消并释放预占。 |
| PARTIALLY_OUTBOUND | 部分出库。已经扣过库存，不能整单取消。 |
| OUTBOUNDED | 已出库。购买数量都已离开库存账面，尚未全部交给承运商。 |
| PARTIALLY_SHIPPED | 部分发货。已经有物流单确认发货。 |
| SHIPPED | 已发货。订单数量都已交给承运商。 |
| COMPLETED | 已完成。全部物流单都已签收。 |

状态只能经提交、确认、取消流转，不要直接改 status 列。
""",
    },
    {
        "filename": "purchase-order-status.md",
        "source_type": "DERIVED",
        "domain": "purchase",
        "scenario": "similar-rule",
        "datasets": ["V8-01-Hard-Cases", "V8-06-Retrieval-Precision"],
        "source_paths": ["services/erp/app/models/purchase.py"],
        "body": """# 采购单状态

来源：`services/erp/app/models/purchase.py` 的 `PurchaseOrderStatus`。

审核通过不改库存；收货确认才增加 quantity。

| 状态 | 代码注释中的含义 |
| --- | --- |
| DRAFT | 草稿。可改供应商、仓库和明细；可提交审核或取消。未入库。 |
| PENDING_APPROVAL | 待审核。可批准进入待收货、驳回，或取消。批准同事务直达待收货，无单独 APPROVED。 |
| WAITING_RECEIPT | 待收货。审核已通过，等待收货入库。可部分收货或一次收完；本版本不可取消。 |
| PARTIALLY_RECEIVED | 部分收货。已有收货单入库，但仍有未收完的明细。 |
| RECEIVED | 已收货。全部明细收齐。终态，不能再流转。 |
| REJECTED | 已驳回。可改单后重新提交，或取消。 |
| CANCELLED | 已取消。终态，不能再流转。 |

采购单批准和销售订单确认不是同一件事：采购批准不增加库存。
""",
    },
    {
        "filename": "purchase-receipt-confirm.md",
        "source_type": "DERIVED",
        "domain": "purchase",
        "scenario": "inventory-increase",
        "datasets": ["V8-02-Multi-Doc", "V8-06-Retrieval-Precision"],
        "source_paths": ["services/erp/app/services/purchase_receipt.py"],
        "body": """# 采购收货确认

来源：`services/erp/app/services/purchase_receipt.py` 模块说明。

草稿收货单不入库。确认收货才增加 quantity，并且和采购进度同一事务。

确认时只加 quantity，不改 reserved。确认逻辑不自己 commit。

这与销售订单确认不同：销售确认写的是预占，采购收货确认增加的是 quantity。
""",
    },
    {
        "filename": "stock-transfer-draft.md",
        "source_type": "DERIVED",
        "domain": "warehouse",
        "scenario": "no-stock-change",
        "datasets": ["V8-01-Hard-Cases", "V8-02-Multi-Doc"],
        "source_paths": ["services/erp/app/services/stock_transfer.py"],
        "body": """# 仓库调拨草稿

来源：`services/erp/app/services/stock_transfer.py`。

提交调拨的代码注释写明：DRAFT → PENDING_OUTBOUND。仍然不改库存。

因此调拨草稿和调拨提交都还没有改库存数量。不要把它说成确认销售订单那样的预占。
""",
    },
    {
        "filename": "outbound-reserved-error.md",
        "source_type": "DERIVED",
        "domain": "outbound",
        "scenario": "error-code",
        "datasets": ["V8-06-Retrieval-Precision", "V8-07-Regression"],
        "source_paths": ["services/erp/app/services/outbound.py"],
        "body": """# 出库超过预占

来源：`services/erp/app/services/outbound.py`。

出库数量超过已预占数量时，接口数据里的 error 为 `OUTBOUND_EXCEEDS_RESERVED`。

该错误码不是 `INSUFFICIENT_RESERVED_INVENTORY`。后者出现在释放预占超过 reserved_quantity 的库存路径。
""",
    },
    {
        "filename": "inventory-release-error.md",
        "source_type": "DERIVED",
        "domain": "inventory",
        "scenario": "error-code",
        "datasets": ["V8-01-Hard-Cases", "V8-06-Retrieval-Precision"],
        "source_paths": ["services/erp/app/services/inventory.py", "services/erp/tests/test_inventory.py"],
        "body": """# 释放预占与盘点冲突

来源：`services/erp/app/services/inventory.py` 与 `services/erp/tests/test_inventory.py`。

释放预占超过 reserved_quantity 时，错误码是 `INSUFFICIENT_RESERVED_INVENTORY`。

盘点调整和预占冲突时，错误码是 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`。测试 `test_stocktake.py` 也断言该错误码。

这两个错误码不能互换，也不能写成出库超额的 `OUTBOUND_EXCEEDS_RESERVED`。
""",
    },
    {
        "filename": "knowledge-processing.md",
        "source_type": "DERIVED",
        "domain": "knowledge",
        "scenario": "pipeline",
        "datasets": ["V8-05-Long-Query", "V8-07-Regression"],
        "source_paths": [
            "services/knowledge/app/core/config.py",
            "services/knowledge/app/processing/extract.py",
            "services/knowledge/app/processing/split.py",
        ],
        "body": """# Knowledge 文档处理边界

来源：Knowledge 配置与解析代码，不是 ERP 库存规则。

上传单文件上限 `max_upload_bytes` 默认为 20MB，单次最多 `max_upload_files` 10 个。允许扩展名包括 pdf、docx、txt、md。

切片长度单位是字符。默认 `default_chunk_size` 800，`default_chunk_overlap` 120。合法范围是 `chunk_size_min` 100 到 `chunk_size_max` 8000，且 overlap 必须小于 chunk_size。

PDF 使用 pypdf 逐页 `extract_text`。扫描版或图片型 PDF 提取不到文本时失败，错误码 40075，明确不支持 OCR。没有页数硬拒绝；超过 `pdf_page_warn`（默认 80）只在 warning 中提示内存随页数增长。

PARSE、CHUNK、EMBED 是不同任务。EMBED 失败不回滚已完成的原文和切片。
""",
    },
    {
        "filename": "knowledge-eval-boundary.md",
        "source_type": "DERIVED",
        "domain": "knowledge",
        "scenario": "evaluation",
        "datasets": ["V8-04-Hallucination", "V8-07-Regression"],
        "source_paths": ["services/knowledge/app/services/evaluation.py", "services/knowledge/app/evaluation/metrics.py"],
        "body": """# 评测不改索引

来源：`services/knowledge/app/services/evaluation.py` 模块说明，以及 `metrics.py`。

评测不修改线上 Chunk 或向量索引。Hit、Recall、Precision、MRR、nDCG 由代码计算，禁止用 LLM 给这些指标打分。

无答案题的 `false_recall` 只表示 Top-K 非空，定义标记为 `top_k_nonempty_not_hallucination_rate`。它不是幻觉率。

LLM Judge 只产生主观的 Faithfulness、Answer Relevancy、Answer Correctness。Judge 失败时不得伪造分数。
""",
    },
    {
        "filename": "iam-knowledge-permission.md",
        "source_type": "DERIVED",
        "domain": "rbac",
        "scenario": "permission-code",
        "datasets": ["V8-06-Retrieval-Precision"],
        "source_paths": ["services/iam/app/core/permissions.py"],
        "body": """# Knowledge 读权限码

来源：`services/iam/app/core/permissions.py` 的 `PermissionCode`。

知识库读取权限码是 `knowledge:read`。这是 IAM 权限枚举中的字符串，不是 ERP 销售订单状态。
""",
    },
    {
        "filename": "long-order-and-stock.md",
        "source_type": "DERIVED",
        "domain": "cross-doc",
        "scenario": "long-context",
        "datasets": ["V8-02-Multi-Doc", "V8-05-Long-Query"],
        "source_paths": [
            "services/erp/app/models/sales_order.py",
            "services/erp/app/models/purchase.py",
            "services/erp/app/services/purchase_receipt.py",
            "services/erp/app/services/stock_transfer.py",
        ],
        "body": """# 订单、收货与调拨对照

本文把四份源码里的结论放在一起，便于跨文档提问。每条都能回到单独文档。

销售订单 DRAFT 未预占库存。确认才会预占库存，确认成功后的待出库状态是 WAITING_OUTBOUND。PARTIALLY_OUTBOUND 已经扣过库存，不能整单取消。

采购单审核通过不改库存。采购收货确认才增加 quantity，并且只加 quantity，不改 reserved。

仓库调拨从 DRAFT 提交到 PENDING_OUTBOUND 时，代码注释写明仍然不改库存。

因此「确认」在销售、采购收货、调拨提交三个动作上的库存效果不同，不能合成一句通用规则。
""",
    },
    {
        "filename": "english-identifiers.md",
        "source_type": "DERIVED",
        "domain": "api",
        "scenario": "exact-token",
        "datasets": ["V8-06-Retrieval-Precision", "V8-05-Long-Query"],
        "source_paths": [
            "services/erp/app/models/sales_order.py",
            "services/erp/app/services/outbound.py",
            "services/iam/app/core/permissions.py",
        ],
        "body": """# Exact identifiers

These strings appear in source code and must be retrieved exactly.

- Class `SalesOrderStatus` includes `PARTIALLY_OUTBOUND` and `WAITING_OUTBOUND`.
- Outbound overflow error is `OUTBOUND_EXCEEDS_RESERVED`.
- IAM permission code is `knowledge:read`.
- Reserved release error is `INSUFFICIENT_RESERVED_INVENTORY`.

中英混合提问时，仍应命中上述标识，而不是同义改写后的中文状态名。
""",
    },
    {
        "filename": "synthetic-noise.md",
        "source_type": "SYNTHETIC",
        "domain": "adversarial",
        "scenario": "noise",
        "datasets": ["V8-01-Hard-Cases", "V8-04-Hallucination"],
        "source_paths": [],
        "body": """# SYNTHETIC 噪声

本文是构造的干扰材料，不是 Neorvion 业务规则。不得当作 Ground Truth。

SYNTHETIC：有人声称销售订单 DRAFT 会立即扣减 quantity。该说法与 `SalesOrderStatus` 注释冲突，只用于考察检索是否把噪声当成证据。

SYNTHETIC：虚构错误码 `MAGIC_STOCK_OVERFLOW` 不存在于当前出库服务。
""",
    },
    {
        "filename": "synthetic-similar-policy.md",
        "source_type": "SYNTHETIC",
        "domain": "adversarial",
        "scenario": "near-miss",
        "datasets": ["V8-04-Hallucination", "V8-03-Unanswerable"],
        "source_paths": [],
        "body": """# SYNTHETIC 相似但无效的制度

本文全部为虚构，标记 SYNTHETIC，与真实状态机分开存放。

SYNTHETIC：虚构的「极速仓」规定，订单支付后 15 分钟必须自动完成，错误码为 `FAST_WAREHOUSE_TIMEOUT`。当前仓库代码没有这个制度，也没有这个错误码。

如果问题询问极速仓超时错误码，正确行为是拒绝回答，而不是引用本文冒充正式规则。评测无答案题不应把本文标成有效相关证据。
""",
    },
]


def _questions() -> list[dict]:
    """题目只引用上文已经写进文档的句子。"""
    rows = [
        ("v8-hard-001", "V8-01-Hard-Cases", "销售订单 DRAFT 会预占库存吗？", "不会。DRAFT 未预占库存。", "FACTUAL", 2, ["order", "reserve"], False, "sales-order-status.md", "未预占库存", "区分草稿和确认"),
        ("v8-hard-002", "V8-01-Hard-Cases", "部分出库的销售订单还能整单取消吗？", "不能。PARTIALLY_OUTBOUND 已经扣过库存，不能整单取消。", "PARAPHRASE", 3, ["cancel"], False, "sales-order-status.md", "不能整单取消", "相似状态下的相反结论"),
        ("v8-hard-003", "V8-01-Hard-Cases", "采购单批准后库存 quantity 会增加吗？", "不会。审核通过不改库存。", "FACTUAL", 3, ["purchase"], False, "purchase-order-status.md", "审核通过不改库存", "和销售确认对照"),
        ("v8-hard-004", "V8-01-Hard-Cases", "调拨从 DRAFT 提交到 PENDING_OUTBOUND 时改库存吗？", "不改。提交调拨仍然不改库存。", "FACTUAL", 3, ["transfer"], False, "stock-transfer-draft.md", "仍然不改库存", "同名状态不同系统"),
        ("v8-hard-005", "V8-01-Hard-Cases", "释放预占超过 reserved_quantity 的错误码是什么？", "INSUFFICIENT_RESERVED_INVENTORY。", "FACTUAL", 2, ["error-code"], False, "inventory-release-error.md", "INSUFFICIENT_RESERVED_INVENTORY", "相近错误码干扰"),
        ("v8-multi-001", "V8-02-Multi-Doc", "销售确认和采购收货确认对库存的影响有什么不同？", "销售确认才会预占库存；采购收货确认才增加 quantity，并且只加 quantity，不改 reserved。", "MULTI_DOC", 4, ["order", "purchase"], False, "long-order-and-stock.md", "库存效果不同", "必须同时看到两种确认"),
        ("v8-multi-002", "V8-02-Multi-Doc", "调拨提交和销售订单确认都会进入某种待出库，它们都预占库存吗？", "不是。销售确认才会预占；调拨提交到 PENDING_OUTBOUND 仍然不改库存。", "MULTI_CONDITION", 4, ["transfer", "order"], False, "long-order-and-stock.md", "仍然不改库存", "跨文档否定"),
        ("v8-multi-003", "V8-02-Multi-Doc", "采购收货确认会修改 reserved 吗？", "不改 reserved。确认时只加 quantity。", "FACTUAL", 3, ["purchase", "reserve"], False, "purchase-receipt-confirm.md", "不改 reserved", "精确字段"),
        ("v8-empty-001", "V8-03-Unanswerable", "极速仓支付后 15 分钟超时的正式错误码是什么？", None, "UNANSWERABLE", 3, ["synthetic", "unanswerable"], True, "synthetic-similar-policy.md", "当前仓库代码没有这个制度", "语料中只有虚构制度，不能当正式答案"),
        ("v8-empty-002", "V8-03-Unanswerable", "Neorvion 当前出库服务是否定义了 MAGIC_STOCK_OVERFLOW？", None, "UNANSWERABLE", 2, ["synthetic", "unanswerable"], True, "synthetic-noise.md", "MAGIC_STOCK_OVERFLOW", "噪声文档不能变成肯定答案"),
        ("v8-empty-003", "V8-03-Unanswerable", "销售订单状态枚举里有 FAST_WAREHOUSE_TIMEOUT 吗？", None, "UNANSWERABLE", 2, ["unanswerable"], True, "sales-order-status.md", "DRAFT", "目标状态机文档没有该码，不能靠检索为空来定性"),
        ("v8-hallu-001", "V8-04-Hallucination", "既然噪声文档说 DRAFT 会扣减 quantity，正式规则是不是也这样？", "不是。正式注释写明 DRAFT 未预占库存。噪声文档标记为 SYNTHETIC。", "HALLUCINATION", 4, ["synthetic"], False, "synthetic-noise.md", "SYNTHETIC", "对抗噪声"),
        ("v8-hallu-002", "V8-04-Hallucination", "评测指标可以由 LLM Judge 直接打出 Recall 吗？", "不可以。Hit、Recall、Precision、MRR、nDCG 由代码计算，禁止用 LLM 给这些指标打分。", "HALLUCINATION", 2, ["eval"], False, "knowledge-eval-boundary.md", "禁止用 LLM 给这些指标打分", "边界题"),
        ("v8-hallu-003", "V8-04-Hallucination", "false_recall 是不是幻觉率？", "不是。它只表示 Top-K 非空，定义是 top_k_nonempty_not_hallucination_rate。", "FACTUAL", 3, ["eval", "metric"], False, "knowledge-eval-boundary.md", "不是幻觉率", "防止指标误读"),
        ("v8-long-001", "V8-05-Long-Query", "请结合销售草稿、部分出库、采购批准和调拨提交，说明哪些动作会改库存。", "销售 DRAFT 未预占；PARTIALLY_OUTBOUND 已经扣过库存；采购批准不改库存；调拨提交仍然不改库存；采购收货确认才增加 quantity。", "LONG", 5, ["order", "purchase", "transfer"], False, "long-order-and-stock.md", "库存效果不同", "长问题需要多条证据"),
        ("v8-long-002", "V8-05-Long-Query", "Knowledge 默认切片长度是多少字符，overlap 能不能大于等于切片长度？", "默认 800 字符，overlap 默认 120，并且 overlap 必须小于 chunk_size。", "MIXED_LANG", 3, ["chunk"], False, "knowledge-processing.md", "overlap 必须小于 chunk_size", "中英参数"),
        ("v8-long-003", "V8-05-Long-Query", "扫描版 PDF 在当前解析器里会 OCR 吗？", "不会。提取不到文本时失败，错误码 40075，明确不支持 OCR。", "FACTUAL", 2, ["pdf"], False, "knowledge-processing.md", "不支持 OCR", "解析边界"),
        ("v8-exact-001", "V8-06-Retrieval-Precision", "出库超过预占时的 error 字符串是什么？", "OUTBOUND_EXCEEDS_RESERVED", "FACTUAL", 2, ["error-code"], False, "outbound-reserved-error.md", "OUTBOUND_EXCEEDS_RESERVED", "精确码"),
        ("v8-exact-002", "V8-06-Retrieval-Precision", "IAM 里知识库读取权限码的准确字符串是什么？", "knowledge:read", "FACTUAL", 1, ["rbac"], False, "iam-knowledge-permission.md", "knowledge:read", "精确权限码"),
        ("v8-exact-003", "V8-06-Retrieval-Precision", "SalesOrderStatus 里表示部分出库的枚举值是什么？", "PARTIALLY_OUTBOUND", "FACTUAL", 2, ["order"], False, "english-identifiers.md", "PARTIALLY_OUTBOUND", "英文标识"),
        ("v8-exact-004", "V8-06-Retrieval-Precision", "采购单有没有单独的 APPROVED 状态？", "没有。批准同事务直达待收货，无单独 APPROVED。", "FACTUAL", 3, ["purchase"], False, "purchase-order-status.md", "无单独 APPROVED", "否定枚举"),
        ("v8-reg-001", "V8-07-Regression", "待出库销售订单在尚未正式出库时可以整单取消吗？", "可以。WAITING_OUTBOUND 尚未正式出库时可以整单取消并释放预占。", "FACTUAL", 2, ["cancel"], False, "sales-order-status.md", "可以整单取消并释放预占", "回归：可取消集合"),
        ("v8-reg-002", "V8-07-Regression", "评测运行会改写线上向量索引吗？", "不会。评测不修改线上 Chunk 或向量索引。", "FACTUAL", 1, ["eval"], False, "knowledge-eval-boundary.md", "不修改线上 Chunk", "回归：评测隔离"),
        ("v8-reg-003", "V8-07-Regression", "盘点与预占冲突的错误码是什么？", "STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY", "FACTUAL", 2, ["error-code"], False, "inventory-release-error.md", "STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY", "回归：错误码"),
        ("v8-reg-004", "V8-07-Regression", "PDF 超过建议页数时当前实现会直接拒绝上传吗？", "不会。超过 pdf_page_warn 只在 warning 中提示，没有页数硬拒绝。", "FACTUAL", 3, ["pdf"], False, "knowledge-processing.md", "没有页数硬拒绝", "回归：大文件边界"),
    ]
    items = []
    for key, dataset, question, answer, qtype, difficulty, tags, unanswerable, doc, quote, goal in rows:
        items.append(
            {
                "external_key": key,
                "dataset": dataset,
                "question": question,
                "expected_answer": answer,
                "question_type": qtype,
                "difficulty": difficulty,
                "tags": tags + ["v8", dataset],
                "is_unanswerable": unanswerable,
                "source_document": doc,
                "evidence_quote": quote,
                "needs_human_review": True,
                "design_goal": goal,
            }
        )
    return items


def documents() -> list[dict]:
    copied = []
    for item in _DOCS:
        body = item["body"].strip() + "\n"
        copied.append({**item, "body": body, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()})
    return copied


def questions() -> list[dict]:
    return _questions()


def validate_catalog() -> dict:
    """检查题包可追溯、无重复键，且证据句真实出现在对应文档中。"""
    docs = {item["filename"]: item for item in documents()}
    errors: list[str] = []
    seen: set[str] = set()
    by_dataset: dict[str, int] = {name: 0 for name in DATASETS}
    pending = 0
    for item in questions():
        key = item["external_key"]
        if key in seen:
            errors.append(f"重复 external_key {key}")
        seen.add(key)
        if item["dataset"] not in DATASETS:
            errors.append(f"{key} 数据集不在 V8 清单")
        by_dataset[item["dataset"]] = by_dataset.get(item["dataset"], 0) + 1
        doc = docs.get(item["source_document"])
        if doc is None:
            errors.append(f"{key} 缺少来源文档")
            continue
        if item["evidence_quote"] not in doc["body"]:
            errors.append(f"{key} 的证据句不在 {item['source_document']}")
        if item["is_unanswerable"] and item["expected_answer"]:
            errors.append(f"{key} 无答案题不应有标准答案")
        if not item["is_unanswerable"] and not item["expected_answer"]:
            errors.append(f"{key} 有答案题缺少标准答案")
        if not item["needs_human_review"]:
            errors.append(f"{key} 不得直接作为正式 Ground Truth")
        if doc["source_type"] == "SYNTHETIC" and not item["is_unanswerable"] and "SYNTHETIC" not in doc["body"]:
            errors.append(f"{key} 的虚构文档未标记 SYNTHETIC")
        pending += 1
    extras = {
        "v8-hallu-001": ("sales-order-status.md", "未预占库存"),
        "v8-empty-003": ("sales-order-status.md", "FAST_WAREHOUSE_TIMEOUT"),
    }
    for item in questions():
        extra = extras.get(item["external_key"])
        if extra is None:
            continue
        filename, token = extra
        body = docs[filename]["body"]
        if item["external_key"] == "v8-empty-003":
            if token in body:
                errors.append("销售订单状态文档不应包含虚构错误码")
        elif token not in body:
            errors.append(f"{item['external_key']} 缺少交叉证据 {token}")
    for doc in docs.values():
        if doc["source_type"] not in {"REAL", "DERIVED", "SYNTHETIC"}:
            errors.append(f"{doc['filename']} 来源类型无效")
        if doc["source_type"] != "SYNTHETIC" and not doc["source_paths"]:
            errors.append(f"{doc['filename']} 非虚构文档缺少来源路径")
    return {
        "ok": not errors,
        "errors": errors,
        "document_count": len(docs),
        "question_count": len(seen),
        "by_dataset": by_dataset,
        "pending_review": pending,
        "ready": 0,
        "missing_chunk_judgments": len(seen),
    }


def experiment_preset_payloads(dataset_id: int) -> list[dict]:
    """四组对照只固定策略和 Rerank。调用方必须自己保证数据集版本和索引不变，本函数不启动 Run。"""
    shared = {
        "top_k": 8,
        "candidate_k": 24,
        "rrf_k": 60,
        "evaluate_generation": False,
    }
    return [
        {
            "dataset_id": dataset_id,
            "name": item["name"],
            "description": "V8 对照配置。不要在创建时自动运行。",
            "config": {**shared, "strategy": item["strategy"], "rerank": item["rerank"]},
        }
        for item in EXPERIMENT_PRESETS
    ]


def materialize() -> dict:
    """把题包写成可导入文件。不上传知识库，不写数据库。"""
    root = FIXTURE_ROOT
    doc_dir = root / "docs"
    doc_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for item in documents():
        path = doc_dir / item["filename"]
        path.write_text(item["body"], encoding="utf-8")
        manifest.append(
            {
                "filename": item["filename"],
                "source_type": item["source_type"],
                "domain": item["domain"],
                "scenario": item["scenario"],
                "source_paths": item["source_paths"],
                "datasets": item["datasets"],
                "sha256": item["sha256"],
                "needs_human_review": True,
                "imported": False,
            }
        )
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "questions.json").write_text(json.dumps(questions(), ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "experiment-presets.json").write_text(
        json.dumps(experiment_preset_payloads(0), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = validate_catalog()
    (root / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
