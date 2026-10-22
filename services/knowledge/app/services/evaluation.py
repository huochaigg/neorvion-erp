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
from app.evaluation.version_diff import diff_snapshots
from app.models.evaluation import (
    AnnotationStatus,
    CaseSource,
    EvaluationCase,
    EvaluationDataset,
    EvaluationDatasetVersion,
    EvaluationExperiment,
    EvaluationJudgment,
    EvaluationRun,
    QuestionType,
    RunStatus,
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
    CaseUpsertBatchIn,
    CaseUpsertResultOut,
    ChatImportIn,
    DatasetCreateIn,
    DatasetListOut,
    DatasetOut,
    DatasetUpdateIn,
    DatasetVersionDetailOut,
    DatasetVersionDiffOut,
    DatasetVersionListOut,
    DatasetVersionOut,
    ExperimentConfigIn,
    ExperimentCreateIn,
    ExperimentListOut,
    ExperimentOut,
    ExperimentUpdateIn,
    ImportResultOut,
    JudgmentIn,
    JudgmentOut,
    RunListOut,
    RunOut,
    SnapshotCaseOut,
    SnapshotJudgmentOut,
    VersionCaseChangeOut,
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


_RUNTIME_IDENTITY_KEYS = (
    "embedding_model",
    "embedding_dimensions",
    "chat_model",
    "rerank_model",
    "prompt_version",
    "judge_prompt_version",
    "metric_version",
    "granularity",
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


def freeze_run_config(experiment_config: dict | None, *, knowledge_base_ids: list[int]) -> dict:
    """冻结本次运行实际使用的模型身份。检索 Top-K 等开关沿用实验配置，缺 key 不补默认值。"""
    config = dict(experiment_config or {})
    runtime = default_experiment_config()
    for key in _RUNTIME_IDENTITY_KEYS:
        config[key] = runtime.get(key)
    if not config.get("knowledge_base_ids"):
        config["knowledge_base_ids"] = list(knowledge_base_ids)
    return config


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
            annotation_status=(
                AnnotationStatus.PENDING.value
                if payload.needs_human_review
                else AnnotationStatus.READY.value
                if unanswerable
                else AnnotationStatus.PENDING.value
            ),
            source=CaseSource.MANUAL.value,
            external_key=(payload.external_key or "").strip() or None,
            needs_human_review=payload.needs_human_review,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return self._case_out(row, [])

    async def upsert_cases(self, dataset_id: int, payload: CaseUpsertBatchIn) -> CaseUpsertResultOut:
        """按 external_key 幂等写入。重复执行更新题目与标注，不新增重复记录。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        await self._require_dataset(dataset_id)
        created = 0
        updated = 0
        skipped = 0
        errors: list[dict] = []
        results: list[CaseOut] = []
        for index, item in enumerate(payload.items, start=1):
            key = (item.external_key or "").strip() or None
            if not key:
                errors.append({"row": index, "message": "缺少 external_key，无法幂等导入"})
                skipped += 1
                continue
            qtype = item.question_type if item.question_type in _TYPES else QuestionType.FACTUAL.value
            unanswerable = item.is_unanswerable or qtype == QuestionType.UNANSWERABLE.value
            row = await self.repo.get_case_by_external_key(dataset_id, key)
            if row is None:
                row = EvaluationCase(
                    tenant_id=self.context.tenant_id,
                    dataset_id=dataset_id,
                    question=item.question.strip(),
                    expected_answer=(item.expected_answer or "").strip() or None,
                    question_type=qtype,
                    difficulty=item.difficulty,
                    tags=item.tags,
                    is_unanswerable=unanswerable,
                    annotation_status=AnnotationStatus.READY.value if unanswerable else AnnotationStatus.PENDING.value,
                    source=CaseSource.AI_SEED.value if item.needs_human_review else CaseSource.IMPORT.value,
                    external_key=key,
                    needs_human_review=item.needs_human_review,
                    created_by=self.context.user_id,
                    updated_by=self.context.user_id,
                )
                self.session.add(row)
                await self.session.flush()
                created += 1
            else:
                row.question = item.question.strip()
                row.expected_answer = (item.expected_answer or "").strip() or None
                row.question_type = qtype
                row.difficulty = item.difficulty
                row.tags = item.tags
                row.is_unanswerable = unanswerable
                row.needs_human_review = item.needs_human_review
                row.updated_by = self.context.user_id
                updated += 1
            if item.judgments:
                existing = await self.repo.list_judgments(row.id)
                for old in existing:
                    await self.session.delete(old)
                await self.session.flush()
                for judgment in item.judgments:
                    try:
                        chunk, document = await self._load_chunk(judgment.chunk_id)
                    except AppError as exc:
                        errors.append({"row": index, "message": exc.message, "chunk_id": judgment.chunk_id})
                        continue
                    digest = content_sha256(chunk.content)
                    stale = chunk.status != ChunkStatus.ACTIVE.value or not chunk.enabled
                    self.session.add(
                        EvaluationJudgment(
                            tenant_id=self.context.tenant_id,
                            dataset_id=dataset_id,
                            case_id=row.id,
                            document_id=document.id,
                            chunk_id=chunk.id,
                            relevance=judgment.relevance,
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
            await self._refresh_stale_for_case(row.id)
            await self._refresh_case_status(row)
            await self.session.flush()
            await self.session.refresh(row)
            judgments = await self.repo.list_judgments(row.id)
            results.append(self._case_out(row, judgments))
        await self.session.commit()
        return CaseUpsertResultOut(
            created=created,
            updated=updated,
            skipped=skipped,
            items=results,
            errors=errors,
        )

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
        if payload.needs_human_review is not None:
            row.needs_human_review = payload.needs_human_review
        if row.question_type == QuestionType.UNANSWERABLE.value:
            row.is_unanswerable = True
        row.updated_by = self.context.user_id
        await self._refresh_case_status(row)
        if payload.needs_human_review is False and row.annotation_status != AnnotationStatus.READY.value:
            raise AppError(
                "有答案题需要至少一条未失效且相关性≥1的切片标注，或将题目标为无答案，才能标为可评测",
                code=40090,
                status_code=400,
            )
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

    async def list_versions(self, dataset_id: int, *, page: int, page_size: int) -> DatasetVersionListOut:
        """列出版本元数据。快照正文由详情接口分页返回。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        dataset = await self._require_dataset(dataset_id)
        rows, total = await self.repo.list_versions_page(dataset.id, page=page, page_size=page_size)
        counts = await self.repo.run_counts_by_version(dataset.id)
        return DatasetVersionListOut(
            items=[self._version_out(row, current=dataset.current_version, run_count=counts.get(row.version, 0)) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
            current_version=dataset.current_version,
        )

    async def get_version_detail(
        self,
        dataset_id: int,
        version: int,
        *,
        page: int,
        page_size: int,
        q: str | None,
    ) -> DatasetVersionDetailOut:
        """只读查看某次冻结时的题目和标注。不回写工作稿。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        dataset = await self._require_dataset(dataset_id)
        row = await self.repo.get_version(dataset.id, version)
        if row is None:
            raise AppError("冻结版本不存在或不可访问", code=40485, status_code=404)
        cases = self._filter_snapshot_cases(row.snapshot, q)
        start = (page - 1) * page_size
        page_items = cases[start : start + page_size]
        snapshot = row.snapshot if isinstance(row.snapshot, dict) else {}
        run_count = await self.repo.count_runs_for_version(dataset.id, row.version)
        return DatasetVersionDetailOut(
            version=self._version_out(row, current=dataset.current_version, run_count=run_count),
            knowledge_base_ids=[int(item) for item in snapshot.get("knowledge_base_ids") or []],
            items=[self._snapshot_case_out(item) for item in page_items],
            total=len(cases),
            page=page,
            page_size=page_size,
            note="这是冻结当时的只读快照。数据集页面上的题目仍是可编辑工作稿，之后的修改不会改写本版本。",
        )

    async def compare_versions(
        self,
        dataset_id: int,
        *,
        left: int,
        right: int,
        page: int,
        page_size: int,
    ) -> DatasetVersionDiffOut:
        """比较两个冻结版本。右版本相对左版本统计新增、删除和修改。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        dataset = await self._require_dataset(dataset_id)
        left_row = await self.repo.get_version(dataset.id, left)
        right_row = await self.repo.get_version(dataset.id, right)
        if left_row is None or right_row is None:
            raise AppError("冻结版本不存在或不可访问", code=40485, status_code=404)
        compared = diff_snapshots(self._snapshot_cases(left_row.snapshot), self._snapshot_cases(right_row.snapshot))
        changes = compared["changes"]
        start = (page - 1) * page_size
        return DatasetVersionDiffOut(
            left_version=left,
            right_version=right,
            added_count=compared["added_count"],
            removed_count=compared["removed_count"],
            modified_count=compared["modified_count"],
            unchanged_count=compared["unchanged_count"],
            items=[
                VersionCaseChangeOut(
                    change=item["change"],
                    case_id=item["case_id"],
                    fields=item["fields"],
                    before=self._snapshot_case_out(item["before"]) if item["before"] else None,
                    after=self._snapshot_case_out(item["after"]) if item["after"] else None,
                )
                for item in changes[start : start + page_size]
            ],
            total=len(changes),
            page=page,
            page_size=page_size,
            note="差异按题目 ID 对齐，只比较两份冻结快照，不比较当前工作稿。",
        )

    async def delete_version(self, dataset_id: int, version: int) -> None:
        """删除没有 Run 引用的历史快照。

        先锁数据集再锁快照，并在同一事务里重数引用。当前最新版本直接拒绝，不回退 current_version。
        """
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        dataset = await self.repo.get_dataset_for_update(dataset_id)
        if dataset is None:
            raise AppError(_UNAVAILABLE_DATASET, code=40480, status_code=404)
        row = await self.repo.get_version_for_update(dataset.id, version)
        if row is None:
            raise AppError("冻结版本不存在或不可访问", code=40485, status_code=404)
        if row.version == dataset.current_version:
            raise AppError("当前最新冻结版本不能删除，也不会回退版本号", code=40983, status_code=409)
        used = await self.repo.count_runs_for_version(dataset.id, row.version)
        if used:
            raise AppError(f"已有 {used} 次评测运行使用该快照，不能删除", code=40984, status_code=409)
        await self.session.delete(row)
        await self.session.commit()

    async def _mark_stale(self, dataset_id: int) -> None:
        cases = await self.repo.list_all_cases(dataset_id)
        for case in cases:
            await self._refresh_stale_for_case(case.id)
            await self._refresh_case_status(case)

    async def _freeze_now(self, dataset_id: int) -> EvaluationDatasetVersion:
        """内部冻结：调用方已完成权限校验，避免评测运行再要求 update。

        锁住数据集行后再递增版本，避免两次冻结写出同一个版本号。
        """
        dataset = await self.repo.get_dataset_for_update(dataset_id)
        if dataset is None:
            raise AppError(_UNAVAILABLE_DATASET, code=40480, status_code=404)
        await self._mark_stale(dataset.id)
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

    async def list_experiments(
        self,
        dataset_id: int | None,
        page: int,
        page_size: int,
        *,
        strategy: str | None = None,
        sort_by: str = "id",
        sort_order: str = "desc",
    ) -> ExperimentListOut:
        """返回实验参数方案。运行状态和指标由运行列表单独查询。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        allowed_strategy = {"VECTOR", "KEYWORD", "HYBRID"}
        if strategy and strategy not in allowed_strategy:
            raise AppError("不支持的检索策略筛选", code=40090, status_code=400)
        allowed_sort = {"id", "created_at"}
        if sort_by not in allowed_sort:
            raise AppError("不支持的排序字段", code=40091, status_code=400)
        order = sort_order if sort_order in {"asc", "desc"} else "desc"
        rows, total = await self.repo.list_experiments(
            dataset_id=dataset_id,
            strategy=strategy,
            sort_by=sort_by,
            sort_order=order,
            page=page,
            page_size=page_size,
        )
        return ExperimentListOut(
            items=[self._experiment_out(experiment) for experiment in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_experiment(self, experiment_id: int) -> ExperimentOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        return self._experiment_out(await self._require_experiment(experiment_id))

    async def list_runs(
        self,
        *,
        experiment_id: int | None,
        status: str | None,
        strategy: str | None,
        sort_by: str,
        sort_order: str,
        page: int,
        page_size: int,
    ) -> RunListOut:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        allowed_status = {item.value for item in RunStatus}
        if status and status not in allowed_status:
            raise AppError("不支持的运行状态筛选", code=40089, status_code=400)
        allowed_strategy = {"VECTOR", "KEYWORD", "HYBRID"}
        if strategy and strategy not in allowed_strategy:
            raise AppError("不支持的检索策略筛选", code=40090, status_code=400)
        allowed_sort = {"id", "created_at", "recall", "mrr", "ndcg", "hit_rate", "latency_p95"}
        if sort_by not in allowed_sort:
            raise AppError("不支持的排序字段", code=40091, status_code=400)
        order = sort_order if sort_order in {"asc", "desc"} else "desc"
        rows, total = await self.repo.list_runs(
            experiment_id=experiment_id,
            status=status,
            strategy=strategy,
            sort_by=sort_by,
            sort_order=order,
            page=page,
            page_size=page_size,
        )
        names = await self.repo.experiment_names([row.experiment_id for row in rows])
        return RunListOut(
            items=[self._run_out(row, experiment_name=names.get(row.experiment_id)) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def delete_experiment(self, experiment_id: int) -> None:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_DELETE,))
        row = await self._require_experiment(experiment_id)
        row.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def _authorize_bases(self, ids: list[int]) -> list[int]:
        if not ids:
            return []
        allowed = []
        from app.services.access import AccessService

        access = AccessService(self.session, self.context)
        for item in ids:
            try:
                row = await access.assert_readable(item)
            except AppError as exc:
                raise AppError("包含无权访问或不存在的知识库", code=40450, status_code=404) from exc
            allowed.append(row.id)
        return allowed

    def _version_out(self, row: EvaluationDatasetVersion, *, current: int, run_count: int) -> DatasetVersionOut:
        is_current = row.version == current
        return DatasetVersionOut(
            id=row.id,
            dataset_id=row.dataset_id,
            version=row.version,
            case_count=row.case_count,
            ready_count=row.ready_count,
            unanswerable_count=row.unanswerable_count,
            stale_judgment_count=row.stale_judgment_count,
            run_count=run_count,
            is_current=is_current,
            deletable=not is_current and run_count == 0,
            created_at=row.created_at,
            created_by=row.created_by,
        )

    def _snapshot_cases(self, snapshot: dict | None) -> list[dict]:
        payload = snapshot if isinstance(snapshot, dict) else {}
        return [item for item in payload.get("cases") or [] if isinstance(item, dict) and item.get("id") is not None]

    def _filter_snapshot_cases(self, snapshot: dict | None, q: str | None) -> list[dict]:
        cases = self._snapshot_cases(snapshot)
        if q:
            needle = q.strip().lower()
            cases = [item for item in cases if needle in str(item.get("question") or "").lower()]
        return sorted(cases, key=lambda item: int(item["id"]))

    def _snapshot_case_out(self, raw: dict) -> SnapshotCaseOut:
        judgments = []
        for item in raw.get("judgments") or []:
            if not isinstance(item, dict) or item.get("chunk_id") is None:
                continue
            judgments.append(
                SnapshotJudgmentOut(
                    chunk_id=int(item["chunk_id"]),
                    document_id=int(item["document_id"]) if item.get("document_id") is not None else None,
                    relevance=int(item.get("relevance") or 0),
                    source_key=item.get("source_key"),
                    chunk_version=int(item["chunk_version"]) if item.get("chunk_version") is not None else None,
                    content_hash=item.get("content_hash"),
                    filename=item.get("filename"),
                    snippet=item.get("snippet"),
                    stale=bool(item.get("stale")),
                )
            )
        tags = raw.get("tags") or []
        return SnapshotCaseOut(
            id=int(raw["id"]),
            question=str(raw.get("question") or ""),
            expected_answer=raw.get("expected_answer"),
            question_type=raw.get("question_type"),
            difficulty=int(raw["difficulty"]) if raw.get("difficulty") is not None else None,
            tags=[str(item) for item in tags] if isinstance(tags, list) else [],
            is_unanswerable=bool(raw.get("is_unanswerable")),
            annotation_status=raw.get("annotation_status"),
            judgments=judgments,
        )

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
        """按标注刷新状态。待人工复核的题目停在待标注或已标注，不能直接变成可评测。"""
        judgments = await self.repo.list_judgments(case.id)
        valid = [item for item in judgments if not item.stale and item.relevance >= 1]
        if case.needs_human_review:
            case.annotation_status = AnnotationStatus.LABELED.value if judgments else AnnotationStatus.PENDING.value
            return
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
            external_key=row.external_key,
            needs_human_review=bool(row.needs_human_review),
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

    @staticmethod
    def _run_out(row: EvaluationRun, *, experiment_name: str | None = None) -> RunOut:
        return RunOut(
            id=row.id,
            experiment_id=row.experiment_id,
            experiment_name=experiment_name,
            dataset_id=row.dataset_id,
            dataset_version=row.dataset_version,
            status=row.status,
            progress=row.progress,
            attempt=row.attempt,
            error_message=row.error_message,
            error_detail=getattr(row, "error_detail", None),
            interrupt_reason=getattr(row, "interrupt_reason", None),
            current_case_id=getattr(row, "current_case_id", None),
            current_stage=getattr(row, "current_stage", None),
            token_budget=getattr(row, "token_budget", None),
            cost_budget_usd=getattr(row, "cost_budget_usd", None),
            config_snapshot=dict(row.config_snapshot or {}),
            dataset_snapshot_meta=dict(row.dataset_snapshot_meta or {}),
            metrics=row.metrics,
            usage=row.usage,
            started_at=row.started_at,
            finished_at=row.finished_at,
            created_at=row.created_at,
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
