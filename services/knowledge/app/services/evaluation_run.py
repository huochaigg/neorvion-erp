"""异步评测执行器。不改线上 Chunk / 向量；LLM 调用期间尽快提交事务。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.evaluation.judge import (
    JUDGE_PROMPT_VERSION,
    collect_chat,
    judge_answer,
    looks_like_refusal,
)
from app.evaluation.metrics import (
    LabeledItem,
    aggregate_retrieval,
    retrieval_metrics,
    unanswerable_retrieval_stats,
)
from app.models.evaluation import (
    AnnotationStatus,
    EvaluationResult,
    EvaluationRun,
    RunStatus,
)
from app.repositories.evaluation import EvaluationRepository
from app.services.authorization import AuthorizationService
from app.services.chat import ChatService
from app.services.evaluation import EvaluationService
from app.services.retrieval import RetrievalService
from app.tasks.queue import enqueue_eval_run

logger = logging.getLogger(__name__)


class EvaluationRunService:
    def __init__(self, session: AsyncSession, context: TenantContext | None = None) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()
        self.repo = EvaluationRepository(session, context.tenant_id if context else 0)

    async def start(self, experiment_id: int) -> EvaluationRun:
        assert self.context is not None
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_CREATE,))
        repo = EvaluationRepository(self.session, self.context.tenant_id)
        experiment = await repo.get_experiment(experiment_id)
        if experiment is None:
            raise AppError("实验不存在或不可访问", code=40482, status_code=404)
        if await repo.find_active_run(experiment.id) is not None:
            raise AppError("该实验已有进行中的评测", code=40981, status_code=409)
        eval_service = EvaluationService(self.session, self.context)
        dataset = await eval_service._require_dataset(experiment.dataset_id)
        if dataset.current_version <= 0:
            version_row = await eval_service._freeze_now(dataset.id)
        else:
            version_row = await repo.get_version(dataset.id, dataset.current_version)
            if version_row is None:
                version_row = await eval_service._freeze_now(dataset.id)
        snapshot = version_row.snapshot or {}
        ready_cases = [
            item
            for item in snapshot.get("cases") or []
            if item.get("annotation_status") == AnnotationStatus.READY.value
        ]
        if not ready_cases:
            raise AppError("没有可用于正式评测的已标注问题", code=40084, status_code=400)
        if len(ready_cases) > settings.eval_max_cases:
            raise AppError(f"超过单任务最大题量 {settings.eval_max_cases}", code=40085, status_code=400)
        config = dict(experiment.config or {})
        config["knowledge_base_ids"] = config.get("knowledge_base_ids") or list(dataset.knowledge_base_ids or [])
        run = EvaluationRun(
            tenant_id=self.context.tenant_id,
            experiment_id=experiment.id,
            dataset_id=dataset.id,
            dataset_version=version_row.version,
            status=RunStatus.QUEUED.value,
            config_snapshot=config,
            dataset_snapshot_meta={
                "version": version_row.version,
                "ready_count": len(ready_cases),
                "unanswerable_count": version_row.unanswerable_count,
                "stale_judgment_count": version_row.stale_judgment_count,
                "comparable": version_row.stale_judgment_count == 0,
                "embedding_model": config.get("embedding_model"),
                "embedding_dimensions": config.get("embedding_dimensions"),
            },
            created_by=self.context.user_id,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        if settings.task_executor == "redis":
            await enqueue_eval_run(run.id)
        else:
            await EvaluationRunService(self.session).execute(run.id)
            refreshed = await EvaluationRepository(self.session, self.context.tenant_id).get_run(run.id)
            return refreshed or run
        return run

    async def cancel(self, run_id: int) -> EvaluationRun:
        assert self.context is not None
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        run = await self.repo.get_run(run_id)
        if run is None:
            raise AppError("评测任务不存在或不可访问", code=40483, status_code=404)
        if run.status not in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
            raise AppError("只能取消排队或运行中的任务", code=40086, status_code=400)
        run.cancel_requested = True
        if run.status == RunStatus.QUEUED.value:
            run.status = RunStatus.CANCELLED.value
            run.finished_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def retry(self, run_id: int) -> EvaluationRun:
        assert self.context is not None
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        run = await self.repo.get_run(run_id)
        if run is None:
            raise AppError("评测任务不存在或不可访问", code=40483, status_code=404)
        if run.status not in {RunStatus.FAILED.value, RunStatus.CANCELLED.value}:
            raise AppError("只能重试失败或已取消的任务", code=40087, status_code=400)
        if await self.repo.find_active_run(run.experiment_id) is not None:
            raise AppError("该实验已有进行中的评测", code=40981, status_code=409)
        await self.repo.delete_results(run.id)
        run.status = RunStatus.QUEUED.value
        run.progress = 0
        run.attempt += 1
        run.cancel_requested = False
        run.error_message = None
        run.metrics = None
        run.usage = None
        run.started_at = None
        run.finished_at = None
        await self.session.commit()
        if settings.task_executor == "redis":
            await enqueue_eval_run(run.id)
        else:
            await EvaluationRunService(self.session).execute(run.id)
        await self.session.refresh(run)
        return run

    async def execute(self, run_id: int) -> None:
        """Worker 入口。使用运行记录上的租户 ID，不再读取客户端租户头。"""
        run = await self.repo.get_run_for_update(run_id) if self.repo.tenant_id == 0 else await _load_run(self.session, run_id)
        if run is None:
            run = await _load_run(self.session, run_id)
        if run is None:
            return
        if run.status == RunStatus.SUCCESS.value:
            return
        if run.status not in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
            return
        if run.cancel_requested:
            run.status = RunStatus.CANCELLED.value
            run.finished_at = datetime.now(UTC)
            await self.session.commit()
            return
        context = TenantContext(
            user_id=run.created_by,
            tenant_id=run.tenant_id,
            member_id=0,
            is_owner=True,
            role="SYSTEM",
            permission_codes=frozenset(item.value for item in PermissionCode),
            token_jti="eval-worker",
        )
        repo = EvaluationRepository(self.session, run.tenant_id)
        version = await repo.get_version(run.dataset_id, run.dataset_version)
        if version is None:
            run.status = RunStatus.FAILED.value
            run.error_message = "数据集快照不存在"
            run.finished_at = datetime.now(UTC)
            await self.session.commit()
            return
        run.status = RunStatus.RUNNING.value
        run.started_at = datetime.now(UTC)
        run.progress = 1
        await self.session.commit()

        config = dict(run.config_snapshot or {})
        cases = [
            item
            for item in (version.snapshot or {}).get("cases") or []
            if item.get("annotation_status") == AnnotationStatus.READY.value
        ]
        retrieval = RetrievalService(self.session, context)
        chat = ChatService(self.session, context)
        token_used = 0
        prompt_tokens = 0
        completion_tokens = 0
        latencies: list[int] = []
        supervised: list[dict] = []
        unanswerable_stats: list[dict] = []
        gen_scores: list[dict] = []
        refuse_hits = 0
        unanswerable_total = 0

        for index, case in enumerate(cases, start=1):
            await self.session.refresh(run)
            if run.cancel_requested:
                run.status = RunStatus.CANCELLED.value
                run.finished_at = datetime.now(UTC)
                await self.session.commit()
                return
            if token_used >= settings.eval_token_budget:
                run.status = RunStatus.FAILED.value
                run.error_message = "超过单任务 Token 预算"
                run.finished_at = datetime.now(UTC)
                await self.session.commit()
                return
            started = datetime.now(UTC)
            try:
                result_row, usage = await self._evaluate_case(
                    run, case, config, retrieval, chat
                )
            except AppError as exc:
                result_row = EvaluationResult(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    case_id=int(case["id"]),
                    question=str(case.get("question") or ""),
                    is_unanswerable=bool(case.get("is_unanswerable")),
                    retrieved=[],
                    error_message=exc.message,
                    latency_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
                )
                usage = None
            except Exception:
                logger.exception("evaluation case failed run=%s case=%s", run.id, case.get("id"))
                result_row = EvaluationResult(
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    case_id=int(case["id"]),
                    question=str(case.get("question") or ""),
                    is_unanswerable=bool(case.get("is_unanswerable")),
                    retrieved=[],
                    error_message="本题评测失败",
                    latency_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
                )
                usage = None
            self.session.add(result_row)
            if result_row.retrieval_metrics and not result_row.is_unanswerable:
                if "skipped" not in result_row.retrieval_metrics:
                    supervised.append(result_row.retrieval_metrics)
            if result_row.retrieval_metrics and result_row.is_unanswerable:
                unanswerable_stats.append(result_row.retrieval_metrics)
                unanswerable_total += 1
                if looks_like_refusal(result_row.answer or ""):
                    refuse_hits += 1
            if result_row.generation_metrics:
                gen_scores.append(result_row.generation_metrics)
            if usage:
                prompt_tokens += int(usage.get("prompt_tokens") or 0)
                completion_tokens += int(usage.get("completion_tokens") or 0)
                token_used += int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
            latencies.append(result_row.latency_ms)
            run.progress = int(index / max(len(cases), 1) * 100)
            await self.session.commit()

        run.metrics = aggregate_retrieval(supervised, unanswerable_rows=unanswerable_stats)
        if unanswerable_total:
            run.metrics["unanswerable_refuse_rate"] = refuse_hits / unanswerable_total
        if gen_scores:
            run.metrics["generation"] = _avg_generation(gen_scores)
            run.metrics["generation"]["subjective"] = True
        run.usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p95_ms": _percentile(latencies, 95),
            "estimated_cost_usd": _estimate_cost(prompt_tokens, completion_tokens),
            "case_count": len(cases),
        }
        run.status = RunStatus.SUCCESS.value
        run.progress = 100
        run.finished_at = datetime.now(UTC)
        await self.session.commit()

    async def _evaluate_case(
        self,
        run: EvaluationRun,
        case: dict,
        config: dict,
        retrieval: RetrievalService,
        chat: ChatService,
    ) -> tuple[EvaluationResult, dict | None]:
        k = int(config.get("top_k") or settings.default_top_k)
        search = await retrieval.search(
            str(case["question"]),
            knowledge_base_ids=list(config.get("knowledge_base_ids") or []),
            strategy=str(config.get("strategy") or "HYBRID"),
            top_k=k,
            candidate_k=int(config.get("candidate_k") or settings.default_candidate_k),
            vector_k=config.get("vector_k"),
            keyword_k=config.get("keyword_k"),
            rrf_k=config.get("rrf_k"),
            similarity_threshold=config.get("similarity_threshold"),
            rerank=bool(config.get("rerank")),
            persist_log=False,
        )
        ranked = [hit.chunk_id for hit in search.hits]
        labeled = [
            LabeledItem(item_id=int(item["chunk_id"]), relevance=int(item["relevance"]))
            for item in case.get("judgments") or []
            if not item.get("stale")
        ]
        if case.get("is_unanswerable"):
            metrics = unanswerable_retrieval_stats(ranked, k)
        elif any(item.relevance >= 1 for item in labeled):
            metrics = retrieval_metrics(ranked, labeled, k=k, granularity="chunk")
            doc_ranked = _unique([hit.document_id for hit in search.hits])
            doc_labeled = _document_labels(case.get("judgments") or [])
            if any(item.relevance >= 1 for item in doc_labeled):
                metrics["document"] = retrieval_metrics(doc_ranked, doc_labeled, k=k, granularity="document")
        else:
            metrics = {"skipped": "no_relevant_labels", "granularity": "chunk"}

        retrieved = [
            {
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
                "filename": hit.filename,
                "content": hit.content[:500],
                "final_rank": hit.final_rank,
                "vector_score": hit.vector_score,
                "keyword_score": hit.keyword_score,
                "rrf_score": hit.rrf_score,
                "rerank_score": hit.rerank_score,
            }
            for hit in search.hits
        ]
        answer = None
        generation_metrics = None
        judge_raw = None
        judge_error = None
        usage = None
        if config.get("evaluate_generation"):
            if not search.hits and case.get("is_unanswerable"):
                from app.services.chat import _REFUSE

                answer = _REFUSE
                generation_metrics = {
                    "faithfulness": 1.0,
                    "answer_relevancy": 1.0,
                    "answer_correctness": None,
                    "refusal": True,
                    "judge_skipped": True,
                }
            else:
                prompt = chat._build_messages(str(case["question"]), search.hits, [])
                answer, usage = await collect_chat(prompt)
                generation_metrics, judge_raw, judge_error = await judge_answer(
                    question=str(case["question"]),
                    answer=answer,
                    contexts=[hit.content for hit in search.hits],
                    expected_answer=case.get("expected_answer"),
                    is_unanswerable=bool(case.get("is_unanswerable")),
                )
                if case.get("is_unanswerable"):
                    generation_metrics = generation_metrics or {}
                    if generation_metrics is not None:
                        generation_metrics["refusal"] = looks_like_refusal(answer)
        return (
            EvaluationResult(
                tenant_id=run.tenant_id,
                run_id=run.id,
                case_id=int(case["id"]),
                question=str(case.get("question") or ""),
                is_unanswerable=bool(case.get("is_unanswerable")),
                retrieved=retrieved,
                retrieval_metrics=metrics,
                answer=answer,
                generation_metrics=generation_metrics,
                judge_model=settings.chat_model if config.get("evaluate_generation") else None,
                judge_prompt_version=JUDGE_PROMPT_VERSION if config.get("evaluate_generation") else None,
                judge_raw=judge_raw,
                judge_error=judge_error,
                latency_ms=search.latency_ms,
                usage=usage,
            ),
            usage,
        )


async def _load_run(session: AsyncSession, run_id: int) -> EvaluationRun | None:
    from sqlalchemy import select

    return await session.scalar(select(EvaluationRun).where(EvaluationRun.id == run_id).with_for_update())


def _unique(values: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _document_labels(judgments: list[dict]) -> list[LabeledItem]:
    best: dict[int, int] = {}
    for item in judgments:
        if item.get("stale"):
            continue
        doc_id = int(item["document_id"])
        rel = int(item["relevance"])
        best[doc_id] = max(rel, best.get(doc_id, 0))
    return [LabeledItem(item_id=key, relevance=value) for key, value in best.items()]


def _avg_generation(rows: list[dict]) -> dict:
    keys = ["faithfulness", "answer_relevancy", "answer_correctness"]
    out: dict = {}
    for key in keys:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        out[key] = sum(values) / len(values) if values else None
    return out


def _percentile(values: list[int], pct: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return float(ordered[index])


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float | None:
    prompt_rate = settings.eval_prompt_token_usd
    completion_rate = settings.eval_completion_token_usd
    if prompt_rate <= 0 and completion_rate <= 0:
        return None
    return (prompt_tokens / 1000) * prompt_rate + (completion_tokens / 1000) * completion_rate
