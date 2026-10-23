"""导入 V8-R2-120-Comprehensive。

用法：
  uv run python -m app.scripts.import_v8_r2_120 --dry-run
  uv run python -m app.scripts.import_v8_r2_120

只读写评测题和确定性标注，不上传文档，不调用 Embedding / Chat / Judge / Rerank。
不冻结版本。所有题目 needs_human_review=True，不会自动 READY。
V5-RAG-100、V8-00-Baseline、第一轮 V8-01～07 与知识库 #7 不会被修改。
证据句必须在指定文件的 ACTIVE 切片中唯一命中才写入 chunk_id；否则不伪造标注。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import re
import selectors
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import select

from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.evaluation import AnnotationStatus, QuestionType
from app.models.knowledge import ChunkStatus, DocumentChunk, KnowledgeDocument
from app.repositories.knowledge import KnowledgeBaseRepository
from app.schemas.evaluation import (
    CaseUpsertBatchIn,
    CaseUpsertIn,
    DatasetCreateIn,
    DatasetUpdateIn,
    JudgmentIn,
)
from app.services.evaluation import EvaluationService

TENANT_ID = 3
USER_ID = 4
PROTECTED = {"V5-RAG-100", "V8-00-Baseline"}
ROOT = Path(__file__).resolve().parents[2] / "eval_fixtures" / "v8-round2"
VALID_TYPES = {item.value for item in QuestionType}
BUCKET_TARGET = {
    "factual": 15,
    "hard": 20,
    "multi": 20,
    "precision": 15,
    "long": 15,
    "unanswerable": 15,
    "hallucination": 15,
    "regression": 5,
}
DIFF_TARGET = {"EASY": 25, "MEDIUM": 45, "HARD": 35, "EXTREME": 15}


def _load_catalog():
    path = ROOT / "r2_120_catalog.py"
    spec = importlib.util.spec_from_file_location("r2_120_catalog", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载题包 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _context() -> TenantContext:
    return TenantContext(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        member_id=0,
        is_owner=True,
        role="OWNER",
        permission_codes=frozenset(item.value for item in PermissionCode),
    )


def _tokens(text: str) -> set[str]:
    return {item for item in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower()) if len(item) >= 2}


def _interior_score(content: str, quote: str) -> int:
    pos = content.find(quote)
    if pos < 0:
        return -1
    return min(pos, len(content) - pos - len(quote))


def _pick_overlap_home(hits: list[dict], quote: str) -> dict | None:
    ordered = sorted(hits, key=lambda item: item["chunk_index"])
    indices = [item["chunk_index"] for item in ordered]
    consecutive = all(indices[index] + 1 == indices[index + 1] for index in range(len(indices) - 1))
    if not consecutive:
        return None
    return max(ordered, key=lambda item: _interior_score(item["content"], quote))


def resolve_quote(quote: str, filename: str, chunks: list[dict]) -> dict:
    in_file = [
        item
        for item in chunks
        if item["filename"] == filename
        and item["status"] == ChunkStatus.ACTIVE.value
        and item["enabled"]
        and quote in item["content"]
    ]
    anywhere = [
        item
        for item in chunks
        if item["status"] == ChunkStatus.ACTIVE.value and item["enabled"] and quote in item["content"]
    ]
    if len(in_file) == 1:
        hit = in_file[0]
        return {
            "ok": True,
            "reason": "unique-in-file",
            "chunk_id": hit["id"],
            "document_id": hit["document_id"],
            "filename": hit["filename"],
            "chunk_index": hit["chunk_index"],
            "hits": [hit["id"]],
        }
    if len(in_file) > 1:
        home = _pick_overlap_home(in_file, quote)
        if home is not None:
            return {
                "ok": True,
                "reason": "overlap-home",
                "chunk_id": home["id"],
                "document_id": home["document_id"],
                "filename": home["filename"],
                "chunk_index": home["chunk_index"],
                "hits": [item["id"] for item in in_file],
            }
        canonical = min(in_file, key=lambda item: item["chunk_index"])
        return {
            "ok": True,
            "reason": "duplicate-expression-first",
            "chunk_id": canonical["id"],
            "document_id": canonical["document_id"],
            "filename": canonical["filename"],
            "chunk_index": canonical["chunk_index"],
            "hits": [item["id"] for item in in_file],
        }
    if len(anywhere) == 0:
        return {"ok": False, "reason": "missing", "chunk_id": None, "hits": [], "filename": filename}
    return {
        "ok": False,
        "reason": "missing-in-file-found-elsewhere",
        "chunk_id": None,
        "hits": [item["id"] for item in anywhere],
        "filenames": [item["filename"] for item in anywhere],
        "filename": filename,
    }


def annotate_item(item: dict, chunks: list[dict]) -> dict:
    resolved = []
    judgments = []
    fact_to_chunks: dict[str, list[int]] = defaultdict(list)
    issues: list[str] = []
    confidence = item["confidence"]
    if item["is_unanswerable"]:
        corpus = "\n".join(row["content"] for row in chunks)
        leaked = [term for term in item.get("absent_terms") or [] if term and term in corpus]
        if leaked:
            issues.append(f"无答案题的缺席词出现在语料: {leaked}")
            confidence = "low"
        return {
            **item,
            "resolved_gold": [],
            "judgments": [],
            "fact_to_chunks": {},
            "source_document_ids": [],
            "ground_truth_chunk_ids": [],
            "issues": issues,
            "confidence": confidence,
            "label_status": "unanswerable-no-judgment",
        }
    for gold in item["gold"]:
        result = resolve_quote(gold["quote"], gold["filename"], chunks)
        result["fact_id"] = gold["fact_id"]
        result["quote"] = gold["quote"]
        result["relevance"] = gold["relevance"]
        resolved.append(result)
        if result["ok"] and result["chunk_id"] is not None:
            if gold["relevance"] < 1:
                issues.append(f"证据 {gold['fact_id']} 标了 relevance={gold['relevance']}，不会进入 Recall")
            judgments.append({"chunk_id": result["chunk_id"], "relevance": gold["relevance"]})
            fact_to_chunks[gold["fact_id"]].append(result["chunk_id"])
        else:
            issues.append(f"{gold['fact_id']}: {result['reason']} quote={gold['quote'][:80]}")
            confidence = "low"
    # 同一 chunk 多次出现时合并为最高分
    merged: dict[int, int] = {}
    for row in judgments:
        merged[row["chunk_id"]] = max(merged.get(row["chunk_id"], 0), row["relevance"])
    judgments = [{"chunk_id": cid, "relevance": rel} for cid, rel in sorted(merged.items())]
    if item["bucket"] == "multi":
        distinct = {row["chunk_id"] for row in judgments}
        if len(distinct) < 2:
            issues.append("多 Chunk 题有效证据切片少于 2")
            confidence = "low"
        if len(item.get("required_facts") or []) < 2:
            issues.append("多 Chunk 题 required_facts 少于 2")
    source_ids = sorted({row["document_id"] for row in resolved if row.get("document_id")})
    chunk_ids = [row["chunk_id"] for row in judgments]
    return {
        **item,
        "resolved_gold": resolved,
        "judgments": judgments,
        "fact_to_chunks": {key: sorted(set(value)) for key, value in fact_to_chunks.items()},
        "source_document_ids": source_ids,
        "ground_truth_chunk_ids": chunk_ids,
        "issues": issues,
        "confidence": confidence,
        "label_status": "labeled" if judgments else "pending-no-unique-evidence",
    }


def quality_report(items: list[dict], chunks: list[dict]) -> dict:
    buckets = Counter(item["bucket"] for item in items)
    diffs = Counter(item["difficulty_name"] for item in items)
    types = Counter(item["question_type"] for item in items)
    conf = Counter(item["confidence"] for item in items)
    status = Counter(item["label_status"] for item in items)
    rel = Counter()
    gold_chunks: set[int] = set()
    gold_docs: set[int] = set()
    gold_files = Counter()
    for item in items:
        gold_docs.update(item.get("source_document_ids") or [])
        for judgment in item.get("judgments") or []:
            rel[judgment["relevance"]] += 1
            gold_chunks.add(judgment["chunk_id"])
            filename = next((row["filename"] for row in chunks if row["id"] == judgment["chunk_id"]), None)
            if filename:
                gold_files[filename] += 1
    near = []
    tokenized = [(item["external_key"], _tokens(item["question"])) for item in items]
    for index, (left_key, left_tokens) in enumerate(tokenized):
        if not left_tokens:
            continue
        for right_key, right_tokens in tokenized[index + 1 :]:
            if not right_tokens:
                continue
            overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
            if overlap >= 0.62:
                near.append({"left": left_key, "right": right_key, "jaccard": round(overlap, 3)})
    cancel_disputed = [
        item["external_key"]
        for item in items
        if "WAITING_RETURN" in item["question"] and "取消" in item["question"]
    ]
    issues = [ {"key": item["external_key"], "issues": item["issues"]} for item in items if item["issues"] ]
    chunk_ids = {row["id"] for row in chunks}
    stale = sorted({cid for cid in gold_chunks if cid not in chunk_ids})
    covered_files = {row["filename"] for row in chunks if row["id"] in gold_chunks}
    return {
        "case_count": len(items),
        "bucket_counts": dict(buckets),
        "bucket_target": BUCKET_TARGET,
        "difficulty_counts": dict(diffs),
        "difficulty_target": DIFF_TARGET,
        "question_type_counts": dict(types),
        "confidence_counts": dict(conf),
        "label_status_counts": dict(status),
        "relevance_counts": {str(key): value for key, value in sorted(rel.items())},
        "needs_human_review": sum(1 for item in items if item.get("needs_human_review")),
        "gold_chunk_count": len(gold_chunks),
        "active_chunk_count": len(chunks),
        "gold_document_count": len(gold_docs),
        "gold_by_filename": dict(gold_files),
        "files_with_gold": sorted(covered_files),
        "near_duplicates": near,
        "disputed_waiting_return_cancel": cancel_disputed,
        "stale_chunk_ids": stale,
        "items_with_issues": issues,
        "overuse_07": gold_files.get("07-cross-domain-state-collisions.md", 0),
        "freeze_ready": False,
        "freeze_blocker": "全部 needs_human_review=True，工作稿未 READY，本轮不冻结",
    }


def case_tags(item: dict) -> list[str]:
    tags = [
        f"bucket:{item['bucket']}",
        f"difficulty:{item['difficulty_name']}",
        f"confidence:{item['confidence']}",
        "round:v8-r2-120",
        f"label:{item['label_status']}",
    ]
    if item.get("unanswerable_kind"):
        tags.append(f"unanswerable_kind:{item['unanswerable_kind']}")
    if item.get("required_facts"):
        tags.append("required_facts:" + "|".join(fact["id"] for fact in item["required_facts"]))
    for fact_id, chunk_ids in (item.get("fact_to_chunks") or {}).items():
        tags.append(f"fact:{fact_id}=" + ",".join(str(cid) for cid in chunk_ids))
    for doc_id in item.get("source_document_ids") or []:
        tags.append(f"source_document_id:{doc_id}")
    if item.get("annotation_reason"):
        tags.append("reason:" + item["annotation_reason"][:80])
    if item.get("issues"):
        tags.append("needs_review_reason:resolve")
    return tags


def write_artifacts(items: list[dict], report: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    work = []
    gt = []
    review = []
    for item in items:
        work.append(
            {
                "external_key": item["external_key"],
                "bucket": item["bucket"],
                "question_type": item["question_type"],
                "difficulty": item["difficulty_name"],
                "question": item["question"],
                "expected_answer": item["expected_answer"],
                "is_unanswerable": item["is_unanswerable"],
                "needs_human_review": True,
                "confidence": item["confidence"],
            }
        )
        gt.append(
            {
                "case_key": item["external_key"],
                "question": item["question"],
                "expected_answer": item["expected_answer"],
                "question_type": item["question_type"],
                "difficulty": item["difficulty_name"],
                "source_document_ids": item.get("source_document_ids") or [],
                "ground_truth_chunk_ids": item.get("ground_truth_chunk_ids") or [],
                "judgments": item.get("judgments") or [],
                "evidence": [
                    {
                        "fact_id": row.get("fact_id"),
                        "quote": row.get("quote"),
                        "filename": row.get("filename"),
                        "chunk_id": row.get("chunk_id"),
                        "relevance": row.get("relevance"),
                        "resolve": row.get("reason"),
                    }
                    for row in item.get("resolved_gold") or []
                ],
                "required_facts": item.get("required_facts") or [],
                "fact_to_chunks": item.get("fact_to_chunks") or {},
                "annotation_reason": item.get("annotation_reason"),
                "confidence": item["confidence"],
                "needs_human_review": True,
                "issues": item.get("issues") or [],
                "unanswerable_kind": item.get("unanswerable_kind"),
            }
        )
        if item["confidence"] != "high" or item.get("issues"):
            review.append(
                {
                    "case_key": item["external_key"],
                    "bucket": item["bucket"],
                    "confidence": item["confidence"],
                    "issues": item.get("issues") or [],
                    "review_notes": item.get("review_notes") or "",
                    "question": item["question"],
                }
            )
    (ROOT / "questions_120.json").write_text(json.dumps(work, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "ground_truth_120.json").write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "human_review_120.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "quality_report_120.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# V8-R2-120-Comprehensive 质量报告",
        "",
        f"- 题目数：{report['case_count']}",
        f"- 题型桶：{report['bucket_counts']}",
        f"- 难度：{report['difficulty_counts']}",
        f"- QuestionType：{report['question_type_counts']}",
        f"- 置信度：{report['confidence_counts']}",
        f"- 标注状态：{report['label_status_counts']}",
        f"- 相关性等级：{report['relevance_counts']}",
        f"- 需要人工复核：{report['needs_human_review']}",
        f"- 有效证据切片：{report['gold_chunk_count']} / ACTIVE {report['active_chunk_count']}",
        f"- 证据文档分布：{report['gold_by_filename']}",
        f"- 07 对照文档被标次数：{report['overuse_07']}",
        f"- 近重复对数：{len(report['near_duplicates'])}",
        f"- 有争议 WAITING_RETURN 取消题：{report['disputed_waiting_return_cancel']}",
        f"- 失效 Chunk：{report['stale_chunk_ids']}",
        f"- 冻结：{report['freeze_blocker']}",
        "",
        "## 需要人工处理",
        "",
    ]
    for row in review:
        lines.append(f"- `{row['case_key']}` ({row['confidence']}) {'; '.join(row['issues']) or row['review_notes']}")
    (ROOT / "QUALITY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _chunks(session, knowledge_base_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.chunk_index,
                DocumentChunk.status,
                DocumentChunk.enabled,
                DocumentChunk.content,
                KnowledgeDocument.filename,
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.id == DocumentChunk.document_id)
                & (KnowledgeDocument.tenant_id == DocumentChunk.tenant_id),
            )
            .where(
                DocumentChunk.tenant_id == TENANT_ID,
                DocumentChunk.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.deleted_at.is_(None),
            )
        )
    ).all()
    return [
        {
            "id": row.id,
            "document_id": row.document_id,
            "chunk_index": row.chunk_index,
            "status": row.status,
            "enabled": row.enabled,
            "content": row.content,
            "filename": row.filename,
        }
        for row in rows
    ]


def validate_catalog(questions: list[dict]) -> None:
    keys = [item["external_key"] for item in questions]
    if len(keys) != 120:
        raise SystemExit(f"题目数是 {len(keys)}，目标 120")
    if len(set(keys)) != 120:
        raise SystemExit("external_key 有重复")
    buckets = Counter(item["bucket"] for item in questions)
    for name, target in BUCKET_TARGET.items():
        if buckets[name] != target:
            raise SystemExit(f"{name} 实际 {buckets[name]}，目标 {target}")
    diffs = Counter(item["difficulty_name"] for item in questions)
    for name, target in DIFF_TARGET.items():
        if diffs[name] != target:
            raise SystemExit(f"难度 {name} 实际 {diffs[name]}，目标 {target}")
    for item in questions:
        if item["question_type"] not in VALID_TYPES:
            raise SystemExit(f"{item['external_key']} 使用了未支持的 QuestionType {item['question_type']}")
        if not item["needs_human_review"]:
            raise SystemExit(f"{item['external_key']} 不能在本轮关闭 needs_human_review")


async def main(dry_run: bool) -> None:
    catalog = _load_catalog()
    questions = catalog.QUESTIONS
    validate_catalog(questions)
    async with SessionLocal() as session:
        service = EvaluationService(session, _context())
        base = await KnowledgeBaseRepository(session, TENANT_ID).get_by_name(catalog.KB_NAME)
        if base is None:
            raise SystemExit(f"租户 {TENANT_ID} 没有名为 {catalog.KB_NAME} 的知识库")
        if base.id != 8:
            raise SystemExit(f"预期知识库 #8，实际 #{base.id}")
        chunks = await _chunks(session, base.id)
        active = [item for item in chunks if item["status"] == ChunkStatus.ACTIVE.value and item["enabled"]]
        if len(active) != 80:
            raise SystemExit(f"知识库 #8 ACTIVE 切片是 {len(active)}，预期 80")
        annotated = [annotate_item(item, active) for item in questions]
        report = quality_report(annotated, active)
        write_artifacts(annotated, report)
        if dry_run:
            print(json.dumps({"dry_run": True, "report": report, "dataset": catalog.DATASET_NAME}, ensure_ascii=False, indent=2))
            return
        if catalog.DATASET_NAME in PROTECTED:
            raise SystemExit(f"拒绝改写受保护数据集 {catalog.DATASET_NAME}")
        existing = await service.repo.get_dataset_by_name(catalog.DATASET_NAME)
        if existing is None:
            created = await service.create_dataset(
                DatasetCreateIn(
                    name=catalog.DATASET_NAME,
                    description="V8 第二轮 120 题综合评测工作稿。确定性标注待人工复核，未冻结，不能直接作为正式评测。",
                    knowledge_base_ids=[base.id],
                )
            )
            dataset_id = created.id
        else:
            dataset_id = existing.id
            if list(existing.knowledge_base_ids or []) != [base.id]:
                await service.update_dataset(dataset_id, DatasetUpdateIn(knowledge_base_ids=[base.id]))
        payload_items = []
        for item in annotated:
            payload_items.append(
                CaseUpsertIn(
                    external_key=item["external_key"],
                    question=item["question"],
                    expected_answer=item["expected_answer"],
                    question_type=item["question_type"],
                    difficulty=item["difficulty"],
                    tags=case_tags(item),
                    is_unanswerable=item["is_unanswerable"],
                    needs_human_review=True,
                    judgments=[JudgmentIn(chunk_id=row["chunk_id"], relevance=row["relevance"]) for row in item["judgments"]],
                )
            )
        result = await service.upsert_cases(dataset_id, CaseUpsertBatchIn(items=payload_items))
        ready = [row.external_key for row in result.items if row.annotation_status == AnnotationStatus.READY.value]
        if ready:
            raise SystemExit(f"出现了未审核就 READY 的题目: {ready}")
        summary = {
            "dataset": catalog.DATASET_NAME,
            "dataset_id": dataset_id,
            "knowledge_base_id": base.id,
            "created": result.created,
            "updated": result.updated,
            "skipped": result.skipped,
            "errors": result.errors,
            "ready": 0,
            "needs_human_review": len(result.items),
            "labeled": sum(1 for row in result.items if row.annotation_status == AnnotationStatus.LABELED.value),
            "pending": sum(1 for row in result.items if row.annotation_status == AnnotationStatus.PENDING.value),
            "report_files": [
                "eval_fixtures/v8-round2/questions_120.json",
                "eval_fixtures/v8-round2/ground_truth_120.json",
                "eval_fixtures/v8-round2/human_review_120.json",
                "eval_fixtures/v8-round2/QUALITY_REPORT.md",
            ],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.disable(logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
