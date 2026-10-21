"""智能初标。草稿和正式标注分开，确认前不会把题目标成 READY。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.evaluation.label_suggest import (
    LabelCandidate,
    estimate_label_calls,
    finalize_label,
    judge_relevance,
)
from app.models.evaluation import (
    AnnotationStatus,
    EvaluationCase,
    EvaluationLabelJob,
    EvaluationLabelSuggestion,
    LabelConfidence,
    LabelJobStatus,
    SuggestionStatus,
)
from app.models.knowledge import ChunkStatus, DocumentChunk, KnowledgeDocument
from app.processing.hashing import content_sha256
from app.repositories.evaluation import EvaluationRepository
from app.schemas.evaluation import JudgmentIn, SuggestionConfirmIn, SuggestionUpdateIn
from app.services.authorization import AuthorizationService
from app.services.evaluation import EvaluationService
from app.services.retrieval import RetrievalService

Judge = Callable[..., Awaitable[dict]]
_FULL_SCAN_LIMIT = 40
_JOB_STALE_AFTER = timedelta(minutes=10)


class LabelSuggestionService:
    def __init__(self, session: AsyncSession, context: TenantContext, *, judge: Judge | None = None) -> None:
        self.session = session
        self.context = context
        self.repo = EvaluationRepository(session, context.tenant_id)
        self.auth = AuthorizationService()
        self.judge = judge or judge_relevance

    async def estimate(
        self,
        dataset_id: int,
        *,
        rerun: bool = False,
        only_failed: bool = False,
        only_rejected: bool = False,
    ) -> dict:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        dataset = await self._dataset(dataset_id)
        cases = await self._cases(dataset.id)
        pending = 0
        skipped = 0
        for case in cases:
            suggestion = await self.repo.get_label_suggestion_by_case(case.id)
            judgments = await self.repo.list_judgments(case.id)
            if self._locked(case, judgments, suggestion) or not self._should_run(
                suggestion, rerun, only_failed, only_rejected
            ):
                skipped += 1
                continue
            pending += 1
        return {
            "dataset_id": dataset.id,
            "case_count": len(cases),
            "pending_cases": pending,
            "skipped_cases": skipped,
            "executed": False,
            **estimate_label_calls(pending),
        }

    async def accept(
        self,
        dataset_id: int,
        *,
        rerun: bool = False,
        only_failed: bool = False,
        only_rejected: bool = False,
    ) -> dict:
        """写入排队任务后立即返回。模型调用由后台任务继续。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        await self._dataset(dataset_id)
        active = await self._expire_active_job(dataset_id)
        if active is not None:
            return _job_out(active, accepted=True, already_running=True)
        plan = await self.estimate(
            dataset_id,
            rerun=rerun,
            only_failed=only_failed,
            only_rejected=only_rejected,
        )
        job = EvaluationLabelJob(
            tenant_id=self.context.tenant_id,
            dataset_id=dataset_id,
            status=LabelJobStatus.QUEUED.value,
            options={"rerun": rerun, "only_failed": only_failed, "only_rejected": only_rejected},
            total=int(plan["pending_cases"]),
            created_by=self.context.user_id,
        )
        self.session.add(job)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            active = await self._expire_active_job(dataset_id)
            if active is None:
                raise
            return _job_out(active, accepted=True, already_running=True)
        await self.session.refresh(job)
        return _job_out(job, accepted=True, already_running=False)

    async def current_job(self, dataset_id: int) -> dict | None:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        await self._dataset(dataset_id)
        await self._expire_active_job(dataset_id)
        job = await self.repo.latest_label_job(dataset_id)
        if job is None:
            return None
        return _job_out(job, accepted=False, already_running=job.status in _ACTIVE_JOBS)

    async def run_job(self, job_id: int) -> None:
        """后台执行。请求里的数据库会话已经结束，这里使用当前服务自己的会话。"""
        job = await self.session.get(EvaluationLabelJob, job_id)
        if job is None or job.tenant_id != self.context.tenant_id:
            return
        if job.status not in _ACTIVE_JOBS:
            return
        job.status = LabelJobStatus.RUNNING.value
        job.started_at = job.started_at or datetime.now(UTC)
        await self.session.commit()
        options = dict(job.options or {})
        try:
            result = await self.suggest(
                job.dataset_id,
                execute=True,
                rerun=bool(options.get("rerun")),
                only_failed=bool(options.get("only_failed")),
                only_rejected=bool(options.get("only_rejected")),
                job=job,
            )
            if result["failed"] and not result["drafted"]:
                job.status = LabelJobStatus.FAILED.value
                job.error_message = "模型调用失败，题目状态保持不变"
            else:
                job.status = LabelJobStatus.SUCCEEDED.value
        except Exception as exc:
            job.status = LabelJobStatus.FAILED.value
            job.error_message = str(exc)[:500]
        job.finished_at = datetime.now(UTC)
        await self.session.commit()

    async def suggest(
        self,
        dataset_id: int,
        *,
        execute: bool,
        rerun: bool = False,
        only_failed: bool = False,
        only_rejected: bool = False,
        job: EvaluationLabelJob | None = None,
    ) -> dict:
        """execute 为 false 时只返回估算。真正跑模型时由后台任务调用。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        plan = await self.estimate(
            dataset_id,
            rerun=rerun,
            only_failed=only_failed,
            only_rejected=only_rejected,
        )
        if not execute:
            return plan
        dataset = await self._dataset(dataset_id)
        base_ids = [int(item) for item in (dataset.knowledge_base_ids or [])]
        cases = await self._cases(dataset.id)
        corpus = await self._corpus(base_ids) if base_ids else []
        created = 0
        failed = 0
        skipped = 0
        for case in cases:
            suggestion = await self.repo.get_label_suggestion_by_case(case.id)
            judgments = await self.repo.list_judgments(case.id)
            if self._locked(case, judgments, suggestion) or not self._should_run(
                suggestion, rerun, only_failed, only_rejected
            ):
                skipped += 1
                continue
            try:
                candidates, warnings = await self._candidates(case, base_ids, corpus)
                raw = await self.judge(
                    question=case.question,
                    expected_answer=case.expected_answer,
                    question_type=case.question_type,
                    is_unanswerable=case.is_unanswerable,
                    candidates=candidates,
                )
                draft = finalize_label(
                    judge=raw,
                    candidates=candidates,
                    is_unanswerable=case.is_unanswerable,
                    question_type=case.question_type,
                    model_name=draft_model_name(),
                )
                if warnings:
                    draft.risk = f"{draft.risk}；{'；'.join(warnings)}" if draft.risk else "；".join(warnings)
                self._save_draft(case, suggestion, draft)
                created += 1
            except Exception as exc:
                self._save_failure(case, suggestion, str(exc)[:500])
                failed += 1
            if job is not None:
                job.drafted = created
                job.failed = failed
                job.skipped = skipped
            await self.session.commit()
        return {**plan, "executed": True, "drafted": created, "failed": failed, "skipped_cases": skipped}

    async def list_suggestions(self, dataset_id: int, *, confidence: str | None, status: str | None) -> list[dict]:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        await self._dataset(dataset_id)
        rows = await self.repo.list_label_suggestions(dataset_id, confidence=confidence, status=status)
        result = []
        for row in rows:
            case = await self.repo.get_case_including_deleted(row.case_id)
            result.append(self._out(row, case))
        return result

    async def update_draft(self, suggestion_id: int, payload: SuggestionUpdateIn) -> dict:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._draft(suggestion_id)
        case = await self._require_live_case(row.case_id)
        if payload.items is not None:
            row.items = await self._checked_items(case.dataset_id, payload.items)
        if payload.confidence is not None:
            row.confidence = _confidence(payload.confidence)
        if payload.rationale is not None:
            row.rationale = payload.rationale.strip()
        if payload.risk is not None:
            row.risk = payload.risk.strip()
        row.review_note = "人工修改了草稿，尚未确认"
        row.reviewed_by = self.context.user_id
        row.reviewed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(row)
        return self._out(row, case)

    async def reject(self, suggestion_id: int, note: str) -> dict:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self._draft(suggestion_id)
        case = await self._require_live_case(row.case_id)
        row.status = SuggestionStatus.REJECTED.value
        row.review_note = note.strip() or "驳回"
        row.reviewed_by = self.context.user_id
        row.reviewed_at = datetime.now(UTC)
        await self.session.commit()
        return self._out(row, case)

    async def delete_suggestion(self, suggestion_id: int) -> None:
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        row = await self.repo.get_label_suggestion(suggestion_id)
        if row is None:
            raise AppError("初标草稿不存在", code=40455, status_code=404)
        await self.session.delete(row)
        await self.session.commit()

    async def confirm(self, dataset_id: int, payload: SuggestionConfirmIn) -> dict:
        """只把人工确认的草稿写成正式标注。已确认的正式标注不会被覆盖。"""
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        await self._dataset(dataset_id)
        rows = await self.repo.list_label_suggestions(dataset_id, confidence=None, status=SuggestionStatus.DRAFT.value)
        wanted = set(payload.suggestion_ids or [])
        confirmed = 0
        errors: list[dict] = []
        evaluation = EvaluationService(self.session, self.context)
        for row in rows:
            if wanted and row.id not in wanted:
                continue
            if payload.only_high and not wanted and row.confidence != LabelConfidence.HIGH.value:
                continue
            case = await self.repo.get_case(row.case_id)
            if case is None:
                errors.append({"suggestion_id": row.id, "message": "题目已从工作稿删除，无法确认"})
                continue
            judgments = await self.repo.list_judgments(case.id)
            if self._locked(case, judgments, None):
                errors.append({"suggestion_id": row.id, "message": "已有人工确认的正式标注，不会覆盖"})
                continue
            items = self._official_items(case, row)
            if items is None:
                errors.append({"suggestion_id": row.id, "message": "没有可写入的相关切片，或无答案结论与题目定义不一致"})
                continue
            case.needs_human_review = False
            case.updated_by = self.context.user_id
            row.status = SuggestionStatus.CONFIRMED.value
            row.reviewed_by = self.context.user_id
            row.reviewed_at = datetime.now(UTC)
            row.review_note = "人工调整后确认" if row.items != row.original_items else "确认模型建议"
            await self.session.flush()
            await evaluation.replace_judgments(case.id, items)
            confirmed += 1
        return {"confirmed": confirmed, "errors": errors}

    async def _expire_active_job(self, dataset_id: int) -> EvaluationLabelJob | None:
        job = await self.repo.latest_label_job(dataset_id)
        if job is None or job.status not in _ACTIVE_JOBS:
            return None
        updated = job.updated_at
        if updated is not None and updated < datetime.now(UTC) - _JOB_STALE_AFTER:
            job.status = LabelJobStatus.FAILED.value
            job.error_message = "任务中断，请重新开始"
            job.finished_at = datetime.now(UTC)
            await self.session.commit()
            return None
        return job

    async def _candidates(
        self,
        case: EvaluationCase,
        base_ids: list[int],
        corpus: list[LabelCandidate],
    ) -> tuple[list[LabelCandidate], list[str]]:
        if not base_ids:
            raise AppError("数据集没有关联知识库", code=40054, status_code=400)
        quote = _tag_value(case.tags, "证据:")
        source = _tag_value(case.tags, "来源:")
        selected: dict[int, LabelCandidate] = {}

        def add(item: LabelCandidate, method: str) -> None:
            current = selected.get(item.chunk_id)
            if current is None:
                selected[item.chunk_id] = LabelCandidate(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    filename=item.filename,
                    content=item.content,
                    chunk_version=item.chunk_version,
                    content_hash=item.content_hash,
                    methods=[method],
                )
                return
            if method not in current.methods:
                current.methods.append(method)

        for item in corpus:
            if quote and quote in item.content:
                add(item, "exact")
            if source and item.filename == source:
                add(item, "source")
            if len(corpus) <= _FULL_SCAN_LIMIT:
                add(item, "fullscan")
        warnings: list[str] = []
        retrieval = RetrievalService(self.session, self.context)
        for strategy in ("KEYWORD", "VECTOR"):
            try:
                found = await retrieval.search(
                    case.question,
                    knowledge_base_ids=base_ids,
                    strategy=strategy,
                    top_k=min(20, max(len(corpus), 1)),
                    candidate_k=min(40, max(len(corpus), 1)),
                    rerank=False,
                    persist_log=False,
                )
            except Exception:
                warnings.append(f"{strategy} 检索失败，已保留其余候选")
                continue
            by_id = {item.chunk_id: item for item in corpus}
            for hit in found.hits:
                candidate = by_id.get(hit.chunk_id)
                if candidate is not None:
                    add(candidate, strategy.lower())
        return list(selected.values()), warnings

    async def _corpus(self, base_ids: list[int]) -> list[LabelCandidate]:
        if not base_ids:
            return []
        tenant_id = self.context.tenant_id
        rows = (
            await self.session.execute(
                select(DocumentChunk, KnowledgeDocument)
                .join(
                    KnowledgeDocument,
                    (KnowledgeDocument.id == DocumentChunk.document_id)
                    & (KnowledgeDocument.tenant_id == DocumentChunk.tenant_id),
                )
                .where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.knowledge_base_id.in_(base_ids),
                    DocumentChunk.status == ChunkStatus.ACTIVE.value,
                    DocumentChunk.enabled.is_(True),
                    KnowledgeDocument.deleted_at.is_(None),
                )
            )
        ).all()
        return [
            LabelCandidate(
                chunk_id=chunk.id,
                document_id=document.id,
                filename=document.filename,
                content=chunk.content,
                chunk_version=chunk.version,
                content_hash=content_sha256(chunk.content),
            )
            for chunk, document in rows
        ]

    def _save_draft(self, case: EvaluationCase, row: EvaluationLabelSuggestion | None, draft) -> None:
        if row is None:
            row = EvaluationLabelSuggestion(
                tenant_id=self.context.tenant_id,
                dataset_id=case.dataset_id,
                case_id=case.id,
                created_by=self.context.user_id,
            )
            self.session.add(row)
        row.status = SuggestionStatus.DRAFT.value
        row.confidence = draft.confidence
        row.verdict = draft.verdict
        row.rationale = draft.rationale
        row.risk = draft.risk
        row.items = draft.items
        row.original_items = draft.items
        row.model_name = draft.model_name
        row.prompt_version = draft.prompt_version
        row.error_message = None
        row.reviewed_by = None
        row.reviewed_at = None
        row.review_note = ""

    def _save_failure(self, case: EvaluationCase, row: EvaluationLabelSuggestion | None, message: str) -> None:
        if row is None:
            row = EvaluationLabelSuggestion(
                tenant_id=self.context.tenant_id,
                dataset_id=case.dataset_id,
                case_id=case.id,
                created_by=self.context.user_id,
                items=[],
                original_items=[],
            )
            self.session.add(row)
        row.status = SuggestionStatus.FAILED.value
        row.confidence = LabelConfidence.LOW.value
        row.verdict = "INSUFFICIENT"
        row.error_message = message
        row.rationale = ""
        row.risk = "模型调用失败，题目状态保持不变"

    async def _checked_items(self, dataset_id: int, items: list) -> list[dict]:
        dataset = await self._dataset(dataset_id)
        allowed = {int(item) for item in (dataset.knowledge_base_ids or [])}
        corpus = {item.chunk_id: item for item in await self._corpus(list(allowed))}
        checked = []
        for item in items:
            candidate = corpus.get(item.chunk_id)
            if candidate is None:
                raise AppError("切片不在该数据集的知识库中", code=40453, status_code=404)
            checked.append(
                {
                    "chunk_id": candidate.chunk_id,
                    "document_id": candidate.document_id,
                    "filename": candidate.filename,
                    "relevance": item.relevance,
                    "reason": item.reason,
                    "excerpt": (item.excerpt or candidate.content[:240])[:500],
                    "chunk_version": candidate.chunk_version,
                    "content_hash": candidate.content_hash,
                    "methods": candidate.methods or ["manual"],
                }
            )
        return checked

    def _official_items(self, case: EvaluationCase, row: EvaluationLabelSuggestion) -> list[JudgmentIn] | None:
        if row.verdict == "UNANSWERABLE":
            if not case.is_unanswerable:
                return None
            return []
        positive = [item for item in row.items or [] if int(item.get("relevance") or 0) >= 1]
        if not positive:
            return None
        return [JudgmentIn(chunk_id=int(item["chunk_id"]), relevance=int(item["relevance"])) for item in positive]

    def _locked(self, case: EvaluationCase, judgments: list, suggestion: EvaluationLabelSuggestion | None) -> bool:
        if suggestion is not None and suggestion.status == SuggestionStatus.CONFIRMED.value:
            return True
        if case.needs_human_review:
            return False
        if case.annotation_status == AnnotationStatus.READY.value or judgments:
            return True
        return False

    def _should_run(
        self,
        suggestion: EvaluationLabelSuggestion | None,
        rerun: bool,
        only_failed: bool,
        only_rejected: bool,
    ) -> bool:
        if suggestion is None:
            return not only_failed and not only_rejected
        if suggestion.status == SuggestionStatus.CONFIRMED.value:
            return False
        if only_failed:
            return suggestion.status == SuggestionStatus.FAILED.value
        if only_rejected:
            return suggestion.status == SuggestionStatus.REJECTED.value
        if suggestion.status == SuggestionStatus.DRAFT.value and not rerun:
            return False
        if suggestion.status == SuggestionStatus.REJECTED.value and not rerun:
            return False
        return True

    async def _dataset(self, dataset_id: int):
        dataset = await self.repo.get_dataset(dataset_id)
        if dataset is None:
            raise AppError("评测数据集不存在或不可访问", code=40450, status_code=404)
        return dataset

    async def _require_live_case(self, case_id: int) -> EvaluationCase:
        case = await self.repo.get_case(case_id)
        if case is None:
            raise AppError("题目已从工作稿删除，无法继续审核。请删除这条初标草稿", code=40057, status_code=400)
        return case

    async def _draft(self, suggestion_id: int) -> EvaluationLabelSuggestion:
        row = await self.repo.get_label_suggestion(suggestion_id)
        if row is None:
            raise AppError("初标草稿不存在", code=40455, status_code=404)
        if row.status != SuggestionStatus.DRAFT.value:
            raise AppError("只有待审核草稿可以修改或驳回", code=40055, status_code=400)
        return row

    async def _cases(self, dataset_id: int) -> list[EvaluationCase]:
        rows, _total = await self.repo.list_cases(dataset_id, status=None, q=None, page=1, page_size=200)
        return rows

    def _out(self, row: EvaluationLabelSuggestion, case: EvaluationCase | None) -> dict:
        case_deleted = case is None or case.deleted_at is not None
        return {
            "id": row.id,
            "dataset_id": row.dataset_id,
            "case_id": row.case_id,
            "question": case.question if case else "",
            "expected_answer": case.expected_answer if case else None,
            "question_type": case.question_type if case else "",
            "is_unanswerable": bool(case.is_unanswerable) if case else False,
            "annotation_status": case.annotation_status if case else "",
            "needs_human_review": bool(case.needs_human_review) if case else False,
            "case_deleted": case_deleted,
            "status": row.status,
            "confidence": row.confidence,
            "verdict": row.verdict,
            "rationale": row.rationale,
            "risk": row.risk,
            "items": list(row.items or []),
            "original_items": list(row.original_items or []),
            "model_name": row.model_name,
            "error_message": row.error_message,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at,
            "review_note": row.review_note,
        }


_ACTIVE_JOBS = {LabelJobStatus.QUEUED.value, LabelJobStatus.RUNNING.value}


def _job_out(job: EvaluationLabelJob, *, accepted: bool, already_running: bool) -> dict:
    return {
        "id": job.id,
        "dataset_id": job.dataset_id,
        "status": job.status,
        "accepted": accepted,
        "already_running": already_running,
        "executed": False,
        "total": job.total,
        "drafted": job.drafted,
        "failed": job.failed,
        "skipped": job.skipped,
        "pending_cases": job.total,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def context_for_label_job(job: EvaluationLabelJob) -> TenantContext:
    """后台任务沿用入队时已经校验过的用户和租户，不读取请求头。"""
    return TenantContext(
        user_id=job.created_by,
        tenant_id=job.tenant_id,
        member_id=0,
        is_owner=False,
        role="MEMBER",
        permission_codes=frozenset(
            {PermissionCode.KNOWLEDGE_READ.value, PermissionCode.KNOWLEDGE_UPDATE.value}
        ),
    )


async def execute_label_job(job_id: int) -> None:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        job = await session.get(EvaluationLabelJob, job_id)
        if job is None:
            return
        service = LabelSuggestionService(session, context_for_label_job(job))
        await service.run_job(job_id)


def draft_model_name() -> str:
    from app.core.config import settings

    return settings.chat_model


def _confidence(value: str) -> str:
    text = value.strip().upper()
    if text not in {item.value for item in LabelConfidence}:
        raise AppError("置信度只能是 HIGH、MEDIUM 或 LOW", code=40056, status_code=400)
    return text


def _tag_value(tags: list, prefix: str) -> str:
    for tag in tags or []:
        text = str(tag)
        if text.startswith(prefix):
            return text.removeprefix(prefix)
    return ""
