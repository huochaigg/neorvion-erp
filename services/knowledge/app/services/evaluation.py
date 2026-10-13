"""评测数据集、标注与实验。不修改线上 Chunk / 向量索引。"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.evaluation.importing import parse_table
from app.models.evaluation import (
    AnnotationStatus,
    CaseSource,
    EvaluationCase,
    EvaluationDataset,
    EvaluationDatasetVersion,
    EvaluationExperiment,
    EvaluationJudgment,
    QuestionType,
)
from app.models.knowledge import ChunkStatus, DocumentChunk, KnowledgeDocument
from app.processing.hashing import content_sha256
from app.repositories.evaluation import EvaluationRepository
from app.repositories.knowledge import KnowledgeBaseRepository
from app.repositories.rag import ConversationRepository
from app.schemas.evaluation import (
    CaseCreateIn,
    CaseListOut,
    CaseOut,
    CaseUpdateIn,
    ChatImportIn,
    DatasetCreateIn,
    DatasetListOut,
    DatasetOut,
    DatasetUpdateIn,
    ExperimentConfigIn,
    ExperimentCreateIn,
    ExperimentListOut,
    ExperimentOut,
    ExperimentUpdateIn,
    ImportResultOut,
    JudgmentIn,
    JudgmentOut,
)
from app.services.authorization import AuthorizationService

_UNAVAILABLE_DATASET = "评测数据集不存在或不可访问"
_UNAVAILABLE_CASE = "评测问题不存在或不可访问"
_TYPES = {item.value for item in QuestionType}


def source_key_for(document: KnowledgeDocument, chunk: DocumentChunk) -> str:
    return (
        f"kb:{chunk.knowledge_base_id}:doc:{document.id}:sha:{document.sha256}"
        f":v:{chunk.version}:i:{chunk.chunk_index}"
    )


def default_experiment_config(payload: ExperimentConfigIn | None = None) -> dict:
    data = (payload or ExperimentConfigIn()).model_dump()
    data.update(
        {
            "embedding_model": settings.embedding_model,
            "embedding_dimensions": settings.embedding_dimensions,
            "chat_model": settings.chat_model,
            "rerank_model": settings.rerank_model or None,
            "prompt_version": "v3-rag-system",
            "judge_prompt_version": "v4-judge-1",
            "metric_version": "v4-chunk-ndcg-exp",
            "granularity": "chunk",
        }
    )
    return data


class EvaluationService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()
        self.repo = EvaluationRepository(session, context.tenant_id)
        self.bases = KnowledgeBaseRepository(session, context.tenant_id)

    async def list_datasets(self, q: str | None, page: int, page_size: int) -> DatasetListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        rows, total = await self.repo.list_datasets(q=q, page=page, page_size=page_size)
        counts = await self.repo.case_counts([row.id for row in rows])
        return DatasetListOut(
            items=[self._dataset_out(row, counts.get(row.id, {})) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_dataset(self, dataset_id: int) -> DatasetOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        row = await self._require_dataset(dataset_id)
        counts = await self.repo.case_counts([row.id])
        return self._dataset_out(row, counts.get(row.id, {}))

    async def create_dataset(self, payload: DatasetCreateIn) -> DatasetOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_CREATE,))
        if await self.repo.get_dataset_by_name(payload.name.strip()) is not None:
            raise AppError("数据集名称已存在", code=40980, status_code=409)
        bases = await self._authorize_bases(payload.knowledge_base_ids)
        row = EvaluationDataset(
            tenant_id=self.context.tenant_id,
            name=payload.name.strip(),
            description=payload.description,
            knowledge_base_ids=bases,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("数据集名称已存在", code=40980, status_code=409) from exc
        await self.session.refresh(row)
        return self._dataset_out(row, {})

    async def update_dataset(self, dataset_id: int, payload: DatasetUpdateIn) -> DatasetOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._require_dataset(dataset_id)
        if payload.name is not None:
            existed = await self.repo.get_dataset_by_name(payload.name.strip(), exclude_id=row.id)
            if existed is not None:
                raise AppError("数据集名称已存在", code=40980, status_code=409)
            row.name = payload.name.strip()
        if payload.description is not None:
            row.description = payload.description
        if payload.knowledge_base_ids is not None:
            row.knowledge_base_ids = await self._authorize_bases(payload.knowledge_base_ids)
        row.updated_by = self.context.user_id
        await self.session.commit()
        await self.session.refresh(row)
        counts = await self.repo.case_counts([row.id])
        return self._dataset_out(row, counts.get(row.id, {}))

    async def delete_dataset(self, dataset_id: int) -> None:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self._require_dataset(dataset_id)
        row.deleted_at = datetime.now(UTC)
        row.updated_by = self.context.user_id
        await self.session.commit()

    async def copy_dataset(self, dataset_id: int) -> DatasetOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_CREATE,))
        source = await self._require_dataset(dataset_id)
        name = f"{source.name} 副本"
        suffix = 2
        while await self.repo.get_dataset_by_name(name) is not None:
            name = f"{source.name} 副本{suffix}"
            suffix += 1
        clone = EvaluationDataset(
            tenant_id=self.context.tenant_id,
            name=name,
            description=source.description,
            knowledge_base_ids=list(source.knowledge_base_ids or []),
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(clone)
        await self.session.flush()
        cases = await self.repo.list_all_cases(source.id)
        judgments = await self.repo.list_judgments_for_dataset(source.id)
        by_case: dict[int, list[EvaluationJudgment]] = {}
        for item in judgments:
            by_case.setdefault(item.case_id, []).append(item)
        for case in cases:
            copied = EvaluationCase(
                tenant_id=self.context.tenant_id,
                dataset_id=clone.id,
                question=case.question,
                expected_answer=case.expected_answer,
                question_type=case.question_type,
                difficulty=case.difficulty,
                tags=list(case.tags or []),
                is_unanswerable=case.is_unanswerable,
                annotation_status=case.annotation_status,
                source=case.source,
                created_by=self.context.user_id,
                updated_by=self.context.user_id,
            )
            self.session.add(copied)
            await self.session.flush()
            for judgment in by_case.get(case.id, []):
                self.session.add(
                    EvaluationJudgment(
                        tenant_id=self.context.tenant_id,
                        dataset_id=clone.id,
                        case_id=copied.id,
                        document_id=judgment.document_id,
                        chunk_id=judgment.chunk_id,
                        relevance=judgment.relevance,
                        source_key=judgment.source_key,
                        chunk_version=judgment.chunk_version,
                        content_hash=judgment.content_hash,
                        filename=judgment.filename,
                        snippet=judgment.snippet,
                        stale=judgment.stale,
                        created_by=self.context.user_id,
                    )
                )
        await self.session.commit()
        await self.session.refresh(clone)
        counts = await self.repo.case_counts([clone.id])
        return self._dataset_out(clone, counts.get(clone.id, {}))

    async def list_cases(
        self,
        dataset_id: int,
        *,
        status: str | None,
        q: str | None,
        page: int,
        page_size: int,
    ) -> CaseListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        await self._require_dataset(dataset_id)
        rows, total = await self.repo.list_cases(dataset_id, status=status, q=q, page=page, page_size=page_size)
        items = []
        for row in rows:
            judgments = await self.repo.list_judgments(row.id)
            items.append(self._case_out(row, judgments))
        return CaseListOut(items=items, total=total, page=page, page_size=page_size)

    async def create_case(self, dataset_id: int, payload: CaseCreateIn) -> CaseOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        await self._require_dataset(dataset_id)
        qtype = payload.question_type if payload.question_type in _TYPES else QuestionType.FACTUAL.value
        unanswerable = payload.is_unanswerable or qtype == QuestionType.UNANSWERABLE.value
        row = EvaluationCase(
            tenant_id=self.context.tenant_id,
            dataset_id=dataset_id,
            question=payload.question.strip(),
            expected_answer=(payload.expected_answer or "").strip() or None,
            question_type=qtype,
            difficulty=payload.difficulty,
            tags=payload.tags,
            is_unanswerable=unanswerable,
            annotation_status=AnnotationStatus.READY.value if unanswerable else AnnotationStatus.PENDING.value,
            source=CaseSource.MANUAL.value,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._case_out(row, [])

    async def update_case(self, case_id: int, payload: CaseUpdateIn) -> CaseOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._require_case(case_id)
        if payload.question is not None:
            row.question = payload.question.strip()
        if payload.expected_answer is not None:
            row.expected_answer = payload.expected_answer.strip() or None
        if payload.question_type is not None:
            row.question_type = payload.question_type if payload.question_type in _TYPES else row.question_type
        if payload.difficulty is not None:
            row.difficulty = payload.difficulty
        if payload.tags is not None:
            row.tags = payload.tags
        if payload.is_unanswerable is not None:
            row.is_unanswerable = payload.is_unanswerable
        if row.question_type == QuestionType.UNANSWERABLE.value:
            row.is_unanswerable = True
        row.updated_by = self.context.user_id
        await self._refresh_case_status(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._case_out(row, await self.repo.list_judgments(row.id))

    async def delete_case(self, case_id: int) -> None:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self._require_case(case_id)
        row.deleted_at = datetime.now(UTC)
        row.updated_by = self.context.user_id
        await self.session.commit()

    async def replace_judgments(self, case_id: int, items: list[JudgmentIn]) -> CaseOut:
        """覆盖本题标注。失效切片会标 stale，不会悄悄当作有效相关。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        case = await self._require_case(case_id)
        existing = await self.repo.list_judgments(case.id)
        for row in existing:
            await self.session.delete(row)
        await self.session.flush()
        for item in items:
            chunk, document = await self._load_chunk(item.chunk_id)
            digest = content_sha256(chunk.content)
            stale = chunk.status != ChunkStatus.ACTIVE.value or not chunk.enabled
            self.session.add(
                EvaluationJudgment(
                    tenant_id=self.context.tenant_id,
                    dataset_id=case.dataset_id,
                    case_id=case.id,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    relevance=item.relevance,
                    source_key=source_key_for(document, chunk),
                    chunk_version=chunk.version,
                    content_hash=digest,
                    filename=document.filename,
                    snippet=chunk.content[:500],
                    stale=stale,
                    created_by=self.context.user_id,
                )
            )
        await self.session.flush()
        await self._refresh_stale_for_case(case.id)
        await self._refresh_case_status(case)
        await self.session.commit()
        await self.session.refresh(case)
        return self._case_out(case, await self.repo.list_judgments(case.id))

    async def refresh_stale(self, dataset_id: int) -> DatasetOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        dataset = await self._require_dataset(dataset_id)
        await self._mark_stale(dataset.id)
        dataset.updated_by = self.context.user_id
        await self.session.commit()
        counts = await self.repo.case_counts([dataset.id])
        return self._dataset_out(dataset, counts.get(dataset.id, {}))

    async def freeze_version(self, dataset_id: int) -> EvaluationDatasetVersion:
        """冻结当前标注快照。含失效标注时仍可冻结，但标记非严格可比。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        return await self._freeze_now(dataset_id)

    async def _mark_stale(self, dataset_id: int) -> None:
        cases = await self.repo.list_all_cases(dataset_id)
        for case in cases:
            await self._refresh_stale_for_case(case.id)
            await self._refresh_case_status(case)

    async def _freeze_now(self, dataset_id: int) -> EvaluationDatasetVersion:
        """内部冻结：调用方已完成权限校验，避免评测运行再要求 update。"""
        dataset = await self._require_dataset(dataset_id)
        await self._mark_stale(dataset.id)
        dataset = await self._require_dataset(dataset_id)
        cases = await self.repo.list_all_cases(dataset.id)
        snapshot_cases = []
        stale_count = 0
        ready = 0
        unanswerable = 0
        for case in cases:
            judgments = await self.repo.list_judgments(case.id)
            stale_count += sum(1 for item in judgments if item.stale)
            if case.annotation_status == AnnotationStatus.READY.value:
                ready += 1
            if case.is_unanswerable:
                unanswerable += 1
            snapshot_cases.append(
                {
                    "id": case.id,
                    "question": case.question,
                    "expected_answer": case.expected_answer,
                    "question_type": case.question_type,
                    "difficulty": case.difficulty,
                    "tags": case.tags,
                    "is_unanswerable": case.is_unanswerable,
                    "annotation_status": case.annotation_status,
                    "judgments": [
                        {
                            "chunk_id": item.chunk_id,
                            "document_id": item.document_id,
                            "relevance": item.relevance,
                            "source_key": item.source_key,
                            "chunk_version": item.chunk_version,
                            "content_hash": item.content_hash,
                            "filename": item.filename,
                            "snippet": item.snippet,
                            "stale": item.stale,
                        }
                        for item in judgments
                    ],
                }
            )
        version = dataset.current_version + 1
        row = EvaluationDatasetVersion(
            tenant_id=self.context.tenant_id,
            dataset_id=dataset.id,
            version=version,
            snapshot={"cases": snapshot_cases, "knowledge_base_ids": list(dataset.knowledge_base_ids or [])},
            case_count=len(cases),
            ready_count=ready,
            unanswerable_count=unanswerable,
            stale_judgment_count=stale_count,
            created_by=self.context.user_id,
        )
        self.session.add(row)
        dataset.current_version = version
        dataset.updated_by = self.context.user_id
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def import_cases(self, dataset_id: int, filename: str, payload: bytes) -> ImportResultOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        await self._require_dataset(dataset_id)
        rows, errors = parse_table(filename, payload)
        if len(rows) > settings.eval_max_cases:
            raise AppError(f"单次最多导入 {settings.eval_max_cases} 条", code=40083, status_code=400)
        for item in rows:
            unanswerable = item.is_unanswerable
            self.session.add(
                EvaluationCase(
                    tenant_id=self.context.tenant_id,
                    dataset_id=dataset_id,
                    question=item.question,
                    expected_answer=item.expected_answer,
                    question_type=item.question_type,
                    difficulty=item.difficulty,
                    tags=item.tags,
                    is_unanswerable=unanswerable,
                    annotation_status=AnnotationStatus.READY.value if unanswerable else AnnotationStatus.PENDING.value,
                    source=CaseSource.IMPORT.value,
                    created_by=self.context.user_id,
                    updated_by=self.context.user_id,
                )
            )
        await self.session.commit()
        return ImportResultOut(succeeded=len(rows), failed=len(errors), errors=errors)

    async def export_cases(self, dataset_id: int) -> str:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        await self._require_dataset(dataset_id)
        cases = await self.repo.list_all_cases(dataset_id)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "question", "expected_answer", "question_type", "difficulty", "tags", "is_unanswerable", "annotation_status"])
        for case in cases:
            writer.writerow(
                [
                    case.id,
                    case.question,
                    case.expected_answer or "",
                    case.question_type,
                    case.difficulty,
                    ",".join(case.tags or []),
                    "1" if case.is_unanswerable else "0",
                    case.annotation_status,
                ]
            )
        return buffer.getvalue()

    async def import_from_chat(self, dataset_id: int, payload: ChatImportIn):
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        await self._require_dataset(dataset_id)
        conversations = ConversationRepository(self.session, self.context.tenant_id)
        conversation = await conversations.get_owned(payload.conversation_id, self.context.user_id)
        if conversation is None:
            raise AppError("会话不存在或不可访问", code=40470, status_code=404)
        messages = await conversations.list_messages(conversation.id)
        candidates = []
        for message in messages:
            if message.role != "USER" or not message.content.strip():
                continue
            candidates.append(
                {
                    "question": message.content.strip(),
                    "source_message_id": message.id,
                    "annotation_status": AnnotationStatus.PENDING.value,
                }
            )
        if not payload.confirm:
            return {"candidates": candidates, "confirmed": False}
        created = []
        for item in candidates:
            row = EvaluationCase(
                tenant_id=self.context.tenant_id,
                dataset_id=dataset_id,
                question=item["question"],
                question_type=QuestionType.FACTUAL.value,
                source=CaseSource.CHAT.value,
                source_message_id=item["source_message_id"],
                annotation_status=AnnotationStatus.PENDING.value,
                created_by=self.context.user_id,
                updated_by=self.context.user_id,
            )
            self.session.add(row)
            created.append(item)
        await self.session.commit()
        return {"candidates": created, "confirmed": True}

    async def create_experiment(self, payload: ExperimentCreateIn) -> ExperimentOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_CREATE,))
        await self._require_dataset(payload.dataset_id)
        config = default_experiment_config(payload.config)
        if payload.config and payload.config.knowledge_base_ids:
            config["knowledge_base_ids"] = await self._authorize_bases(payload.config.knowledge_base_ids)
        row = EvaluationExperiment(
            tenant_id=self.context.tenant_id,
            dataset_id=payload.dataset_id,
            name=payload.name.strip(),
            description=payload.description,
            config=config,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._experiment_out(row)

    async def update_experiment(self, experiment_id: int, payload: ExperimentUpdateIn) -> ExperimentOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._require_experiment(experiment_id)
        if payload.name is not None:
            row.name = payload.name.strip()
        if payload.description is not None:
            row.description = payload.description
        if payload.config is not None:
            config = default_experiment_config(payload.config)
            if payload.config.knowledge_base_ids:
                config["knowledge_base_ids"] = await self._authorize_bases(payload.config.knowledge_base_ids)
            row.config = config
        row.updated_by = self.context.user_id
        await self.session.commit()
        await self.session.refresh(row)
        return self._experiment_out(row)

    async def copy_experiment(self, experiment_id: int) -> ExperimentOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_CREATE,))
        source = await self._require_experiment(experiment_id)
        row = EvaluationExperiment(
            tenant_id=self.context.tenant_id,
            dataset_id=source.dataset_id,
            name=f"{source.name} 副本",
            description=source.description,
            config=dict(source.config or {}),
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._experiment_out(row)

    async def list_experiments(self, dataset_id: int | None, page: int, page_size: int) -> ExperimentListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        rows, total = await self.repo.list_experiments(dataset_id=dataset_id, page=page, page_size=page_size)
        return ExperimentListOut(
            items=[self._experiment_out(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_experiment(self, experiment_id: int) -> ExperimentOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        return self._experiment_out(await self._require_experiment(experiment_id))

    async def delete_experiment(self, experiment_id: int) -> None:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self._require_experiment(experiment_id)
        row.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def _authorize_bases(self, ids: list[int]) -> list[int]:
        if not ids:
            return []
        allowed = []
        for item in ids:
            row = await self.bases.get_in_tenant(item)
            if row is None:
                raise AppError("包含无权访问或不存在的知识库", code=40450, status_code=404)
            allowed.append(row.id)
        return allowed

    async def _require_dataset(self, dataset_id: int) -> EvaluationDataset:
        row = await self.repo.get_dataset(dataset_id)
        if row is None:
            raise AppError(_UNAVAILABLE_DATASET, code=40480, status_code=404)
        return row

    async def _require_case(self, case_id: int) -> EvaluationCase:
        row = await self.repo.get_case(case_id)
        if row is None:
            raise AppError(_UNAVAILABLE_CASE, code=40481, status_code=404)
        await self._require_dataset(row.dataset_id)
        return row

    async def _require_experiment(self, experiment_id: int):
        row = await self.repo.get_experiment(experiment_id)
        if row is None:
            raise AppError("实验不存在或不可访问", code=40482, status_code=404)
        return row

    async def _load_chunk(self, chunk_id: int) -> tuple[DocumentChunk, KnowledgeDocument]:
        chunk = await self.session.scalar(
            select_chunk(self.context.tenant_id, chunk_id)
        )
        if chunk is None:
            raise AppError("切片不存在或不可访问", code=40453, status_code=404)
        document = await self.session.scalar(
            select_document(self.context.tenant_id, chunk.document_id)
        )
        if document is None:
            raise AppError("文档不存在或不可访问", code=40452, status_code=404)
        return chunk, document

    async def _refresh_stale_for_case(self, case_id: int) -> None:
        for judgment in await self.repo.list_judgments(case_id):
            chunk = await self.session.scalar(select_chunk(self.context.tenant_id, judgment.chunk_id))
            if chunk is None or chunk.status != ChunkStatus.ACTIVE.value:
                judgment.stale = True
                continue
            digest = content_sha256(chunk.content)
            judgment.stale = digest != judgment.content_hash or chunk.version != judgment.chunk_version

    async def _refresh_case_status(self, case: EvaluationCase) -> None:
        judgments = await self.repo.list_judgments(case.id)
        valid = [item for item in judgments if not item.stale and item.relevance >= 1]
        if case.is_unanswerable:
            case.annotation_status = AnnotationStatus.READY.value
        elif valid:
            case.annotation_status = AnnotationStatus.READY.value
        elif judgments:
            case.annotation_status = AnnotationStatus.LABELED.value
        else:
            case.annotation_status = AnnotationStatus.PENDING.value

    def _dataset_out(self, row: EvaluationDataset, counts: dict) -> DatasetOut:
        return DatasetOut(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            description=row.description,
            knowledge_base_ids=list(row.knowledge_base_ids or []),
            current_version=row.current_version,
            pending_count=int(counts.get("PENDING") or 0),
            labeled_count=int(counts.get("LABELED") or 0),
            ready_count=int(counts.get("READY") or 0),
            total_cases=int(counts.get("total") or 0),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _case_out(self, row: EvaluationCase, judgments: list[EvaluationJudgment]) -> CaseOut:
        return CaseOut(
            id=row.id,
            dataset_id=row.dataset_id,
            question=row.question,
            expected_answer=row.expected_answer,
            question_type=row.question_type,
            difficulty=row.difficulty,
            tags=list(row.tags or []),
            is_unanswerable=row.is_unanswerable,
            annotation_status=row.annotation_status,
            source=row.source,
            judgments=[
                JudgmentOut(
                    id=item.id,
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    relevance=item.relevance,
                    source_key=item.source_key,
                    chunk_version=item.chunk_version,
                    filename=item.filename,
                    snippet=item.snippet,
                    stale=item.stale,
                )
                for item in judgments
            ],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _experiment_out(row: EvaluationExperiment) -> ExperimentOut:
        return ExperimentOut(
            id=row.id,
            dataset_id=row.dataset_id,
            name=row.name,
            description=row.description,
            config=dict(row.config or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def select_chunk(tenant_id: int, chunk_id: int):
    from sqlalchemy import select

    return select(DocumentChunk).where(
        DocumentChunk.tenant_id == tenant_id,
        DocumentChunk.id == chunk_id,
    )


def select_document(tenant_id: int, document_id: int):
    from sqlalchemy import select

    return select(KnowledgeDocument).where(
        KnowledgeDocument.tenant_id == tenant_id,
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.deleted_at.is_(None),
    )
