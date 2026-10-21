"""把已有 V8 题包导入租户 3 的测试知识库。

用法：uv run python -m app.scripts.import_v8_questions

只读写评测题和标注，不上传文档，不调用 Embedding 或 Judge。
V5-RAG-100 与 V8-00-Baseline 不会被修改。
证据句只在一个 ACTIVE 切片中出现时，写入相关性 3 的建议标注。
同一句出现在多个切片，或题目是无答案题时，不写标注。
所有题目保持待人工复核，不会标成 READY。
"""

from __future__ import annotations

import asyncio
import json
import logging
import selectors
from pathlib import Path

from sqlalchemy import select

from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.session import SessionLocal
from app.models.evaluation import AnnotationStatus
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
KB_NAME = "测试知识库"
PROTECTED = {"V5-RAG-100", "V8-00-Baseline"}
ROOT = Path(__file__).resolve().parents[2] / "eval_fixtures" / "v8"
SUGGESTED_RELEVANCE = 3


def _context() -> TenantContext:
    return TenantContext(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        member_id=0,
        is_owner=True,
        role="OWNER",
        permission_codes=frozenset(item.value for item in PermissionCode),
    )


def _match(quote: str, chunks: list[dict]) -> list[dict]:
    return [item for item in chunks if item["status"] == ChunkStatus.ACTIVE.value and item["enabled"] and quote in item["content"]]


async def _chunks(session, knowledge_base_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(DocumentChunk.id, DocumentChunk.status, DocumentChunk.enabled, DocumentChunk.content, KnowledgeDocument.filename)
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.id == DocumentChunk.document_id) & (KnowledgeDocument.tenant_id == DocumentChunk.tenant_id),
            )
            .where(
                DocumentChunk.tenant_id == TENANT_ID,
                DocumentChunk.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.deleted_at.is_(None),
            )
        )
    ).all()
    return [
        {"id": row.id, "status": row.status, "enabled": row.enabled, "content": row.content, "filename": row.filename}
        for row in rows
    ]


async def main() -> None:
    questions = json.loads((ROOT / "questions.json").read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for item in questions:
        grouped.setdefault(item["dataset"], []).append(item)
    report = []
    async with SessionLocal() as session:
        service = EvaluationService(session, _context())
        base = await KnowledgeBaseRepository(session, TENANT_ID).get_by_name(KB_NAME)
        if base is None:
            raise SystemExit(f"租户 {TENANT_ID} 没有名为{KB_NAME}的知识库")
        chunks = await _chunks(session, base.id)
        for name, items in grouped.items():
            if name in PROTECTED:
                raise SystemExit(f"拒绝改写受保护数据集 {name}")
            existing = await service.repo.get_dataset_by_name(name)
            if existing is None:
                created = await service.create_dataset(
                    DatasetCreateIn(
                        name=name,
                        description="V8 题包导入。题目和标注都待人工复核，不能直接作为正式评测。",
                        knowledge_base_ids=[base.id],
                    )
                )
                dataset_id = created.id
            else:
                dataset_id = existing.id
                if list(existing.knowledge_base_ids or []) != [base.id]:
                    await service.update_dataset(dataset_id, DatasetUpdateIn(knowledge_base_ids=[base.id]))
            payload_items = []
            for item in items:
                hits = [] if item["is_unanswerable"] else _match(item["evidence_quote"], chunks)
                judgments = [JudgmentIn(chunk_id=hits[0]["id"], relevance=SUGGESTED_RELEVANCE)] if len(hits) == 1 else []
                reason = "无答案题不写标注" if item["is_unanswerable"] else ("唯一证据切片" if len(hits) == 1 else ("证据句出现在多个切片，待人工确认" if hits else "没有切片包含证据句"))
                report.append(
                    {
                        "external_key": item["external_key"],
                        "dataset": name,
                        "reason": reason,
                        "chunk_ids": [hit["id"] for hit in hits],
                        "filenames": [hit["filename"] for hit in hits],
                        "written": len(judgments) == 1,
                    }
                )
                tags = list(item["tags"])
                if item.get("source_document"):
                    tags.append(f"来源:{item['source_document']}")
                if item.get("evidence_quote"):
                    tags.append(f"证据:{item['evidence_quote']}")
                if hits and not judgments:
                    for hit in hits:
                        tags.append(f"待确认:{hit['id']}:{hit['filename']}")
                payload_items.append(
                    CaseUpsertIn(
                        external_key=item["external_key"],
                        question=item["question"],
                        expected_answer=item["expected_answer"],
                        question_type=item["question_type"],
                        difficulty=item["difficulty"],
                        tags=tags,
                        is_unanswerable=item["is_unanswerable"],
                        needs_human_review=True,
                        judgments=judgments,
                    )
                )
            result = await service.upsert_cases(dataset_id, CaseUpsertBatchIn(items=payload_items))
            ready = [row.external_key for row in result.items if row.annotation_status == AnnotationStatus.READY.value]
            if ready:
                raise SystemExit(f"{name} 出现了未审核就 READY 的题目: {ready}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.disable(logging.INFO)
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
