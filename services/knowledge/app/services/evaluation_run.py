"""异步评测执行器。按 Run+Case+Stage 落 checkpoint，崩溃后从中断处续跑。"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from neorvion_db import PrivilegedOperation, open_privileged_async_session, privileged_option
from neorvion_security import SecurityError
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.iam import snapshot_store
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.db.isolation import REGISTRY
from app.db.session import engine, open_tenant_session
from app.db.system_access import PRIVILEGED_CALLERS
from app.evaluation.budget import (
    accumulate_results,
    assert_budget,
    cost_of,
    estimate_next_call,
    merge_embedding_usage,
    tokens_of,
)
from app.evaluation.citation import citation_metrics
from app.evaluation.context_pack import (
    generation_text,
    pack_retrieved_hits,
    prompt_observability,
    retrieval_diagnostics,
)
from app.evaluation.diagnose import citation_presence, generation_contexts, unanswerable_outcome
from app.evaluation.generation import (
    GENERATION_METRIC_VERSION,
    absent_terms_from_case,
    aggregate_generation,
    fabricated_terms,
    gold_chunk_ids,
    is_false_premise_case,
    prompt_evidence_coverage,
    support_chunk_ids,
)
from app.evaluation.judge import (
    JUDGE_PROMPT_VERSION,
    collect_chat,
    judge_answer,
    looks_like_refusal,
)
from app.evaluation.evidence import (
    LiveChunk,
    classify_evidence_chunks,
    evidence_coverage_metrics,
    parse_case_evidence,
)
from app.evaluation.prompt import assert_no_answer_leak
from app.evaluation.metrics import (
    LabeledItem,
    aggregate_retrieval,
    retrieval_metrics,
    unanswerable_retrieval_stats,
)
from app.evaluation.retry import call_with_retry, interrupt_diagnostics
from app.evaluation.stages import (
    CONTEXT_OVERFLOW_CODES,
    EvalStage,
    InterruptReason,
    PauseRun,
    ResultCaseStatus,
    StageStatus,
    empty_stages,
    interrupt_code_reason,
    mark_stage,
    stage_entry,
    stage_status,
    stage_succeeded,
)
from app.models.evaluation import (
    ACTIVE_RUN_STATUSES,
    AnnotationStatus,
    EvaluationResult,
    EvaluationRun,
    RunStatus,
)
from app.models.knowledge import DocumentChunk
from app.repositories.evaluation import EvaluationRepository
from app.repositories.knowledge import KnowledgeBaseRepository
from app.schemas.ops import ProbeOut
from app.services.authorization import AuthorizationService
from app.services.chat import ChatService
from app.services.evaluation import EvaluationService, default_experiment_config, freeze_run_config
from app.services.retrieval import RetrievalService, RetrievedHit
from app.tasks.queue import enqueue_eval_run

logger = logging.getLogger(__name__)


async def _read_run_tenant(run_id: int) -> int | None:
    """内联执行前只从运行行读取租户。队列里的 id 不能代替这一行。"""
    from app.models.evaluation import EvaluationRun

    async with open_privileged_async_session(
        PrivilegedOperation.WORKER_CLAIM,
        registry=REGISTRY,
        allowed_callers=PRIVILEGED_CALLERS[PrivilegedOperation.WORKER_CLAIM],
        bind=engine,
    ) as privileged:
        session = cast(AsyncSession, cast(object, privileged))
        run = await session.scalar(
            select(EvaluationRun)
            .where(EvaluationRun.id == run_id)
            .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
        )
        if run is None or type(run.tenant_id) is not int or run.tenant_id <= 0:
            return None
        return run.tenant_id


async def execute_eval_run(run_id: int) -> None:
    """独立租户会话执行评测。请求级 Session 在响应后会关闭，不能复用。"""
    tenant_id = await _read_run_tenant(run_id)
    if tenant_id is None:
        logger.error("eval run missing tenant run_id=%s", run_id)
        return
    try:
        async with open_tenant_session(tenant_id) as session:
            await EvaluationRunService(session).execute(run_id)
    except PauseRun:
        logger.info("eval run paused run_id=%s", run_id)
    except Exception:
        logger.exception("eval run crashed run_id=%s", run_id)


def _auth_interrupt(exc: SecurityError) -> tuple[str, bool]:
    """区分暂时不可用和确定性拒绝。第二个值表示应终止，而不是暂停后自动重试。"""
    if exc.status_code == 503 or exc.code in {50313, 40321, 40310}:
        return InterruptReason.SNAPSHOT_UNAVAILABLE.value, False
    if exc.code in {40311, 40312, 40320, 40104, 40410} or exc.status_code == 403:
        return InterruptReason.FORBIDDEN.value, True
    return InterruptReason.SNAPSHOT_UNAVAILABLE.value, False


class EvaluationRunService:
    def __init__(self, session: AsyncSession, context: TenantContext | None = None) -> None:
        self.session = session
        self.context = context
        self.auth = AuthorizationService()
        self.repo = EvaluationRepository(session, context.tenant_id if context else None)
        self.lease_owner = f"{os.getpid()}:{uuid.uuid4().hex[:8]}"

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
        dataset, version_row = await self._locked_snapshot(eval_service, experiment.dataset_id)
        snapshot = version_row.snapshot or {}
        config = freeze_run_config(
            dict(experiment.config or {}),
            knowledge_base_ids=list(dataset.knowledge_base_ids or []),
        )
        ready_cases = _filter_eval_cases(list(snapshot.get("cases") or []), config)
        if not ready_cases:
            raise AppError("没有可用于正式评测的已标注问题", code=40084, status_code=400)
        if len(ready_cases) > settings.eval_max_cases:
            raise AppError(f"超过单任务最大题量 {settings.eval_max_cases}", code=40085, status_code=400)
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
            token_budget=int(config.get("token_budget") or settings.eval_token_budget),
            cost_budget_usd=config.get("cost_budget_usd"),
            created_by=self.context.user_id,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        if settings.task_executor == "redis":
            await enqueue_eval_run(run.id)
        return run

    async def _locked_snapshot(self, eval_service: EvaluationService, dataset_id: int):
        """锁住数据集和当前快照后再创建 Run，避免读到的版本在提交前被删掉。

        尚未冻结时会先冻结并提交；提交后重新加锁，Run 使用加锁时的最新版本。
        """
        dataset = await self.repo.get_dataset_for_update(dataset_id)
        if dataset is None:
            raise AppError("评测数据集不存在或不可访问", code=40480, status_code=404)
        if dataset.current_version <= 0:
            await eval_service._freeze_now(dataset.id)
            dataset = await self.repo.get_dataset_for_update(dataset_id)
        if dataset is None:
            raise AppError("评测数据集不存在或不可访问", code=40480, status_code=404)
        version_row = await self.repo.get_version_for_update(dataset.id, dataset.current_version)
        if version_row is None:
            await eval_service._freeze_now(dataset.id)
            dataset = await self.repo.get_dataset_for_update(dataset_id)
            if dataset is None:
                raise AppError("评测数据集不存在或不可访问", code=40480, status_code=404)
            version_row = await self.repo.get_version_for_update(dataset.id, dataset.current_version)
        if version_row is None:
            raise AppError("数据集快照不存在", code=40485, status_code=404)
        return dataset, version_row

    async def cancel(self, run_id: int) -> EvaluationRun:
        assert self.context is not None
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        run = await self._require_run(run_id)
        if run.status not in set(ACTIVE_RUN_STATUSES):
            raise AppError("只能取消排队、运行中或已暂停的任务", code=40086, status_code=400)
        run.cancel_requested = True
        run.interrupt_reason = InterruptReason.CANCELLED.value
        if run.status in {RunStatus.QUEUED.value, RunStatus.PAUSED.value}:
            run.status = RunStatus.CANCELLED.value
            run.finished_at = datetime.now(UTC)
            run.lease_owner = None
            run.lease_until = None
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def pause(self, run_id: int) -> EvaluationRun:
        """用户主动暂停。QUEUED 立即 PAUSED；RUNNING 在下一题前退出。"""
        assert self.context is not None
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        run = await self._require_run(run_id)
        if run.status not in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
            raise AppError("只能暂停排队或运行中的任务", code=40094, status_code=400)
        run.pause_requested = True
        run.interrupt_reason = InterruptReason.USER_PAUSE.value
        run.error_message = "用户暂停"
        if run.status == RunStatus.QUEUED.value:
            run.status = RunStatus.PAUSED.value
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def resume(self, run_id: int, *, token_budget: int | None = None, cost_budget_usd: float | None = None) -> EvaluationRun:
        """同一 Run 继续。只允许改预算，不得改检索快照。"""
        assert self.context is not None
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        run = await self._require_run(run_id)
        if run.status not in {RunStatus.PAUSED.value, RunStatus.FAILED.value}:
            raise AppError("只能继续已暂停或失败的任务", code=40095, status_code=400)
        other = await self.repo.find_active_run(run.experiment_id)
        if other is not None and other.id != run.id:
            raise AppError("该实验已有进行中的评测", code=40981, status_code=409)
        blocked = await self._resume_blocked_reason(run)
        if blocked:
            raise AppError(blocked, code=40982, status_code=409)
        if token_budget is not None:
            if token_budget < 0:
                raise AppError("Token 预算不能为负", code=40096, status_code=400)
            run.token_budget = token_budget
        if cost_budget_usd is not None:
            if cost_budget_usd < 0:
                raise AppError("费用预算不能为负", code=40096, status_code=400)
            run.cost_budget_usd = cost_budget_usd
        run.status = RunStatus.QUEUED.value
        run.pause_requested = False
        run.cancel_requested = False
        run.finished_at = None
        run.error_message = None
        run.interrupt_reason = None
        run.lease_owner = None
        run.lease_until = None
        await self.session.commit()
        if settings.task_executor == "redis":
            await enqueue_eval_run(run.id)
        await self.session.refresh(run)
        return run

    async def retry_failed(self, run_id: int) -> EvaluationRun:
        """只重置失败/未完成题目的可重试阶段，已成功题目保留。"""
        assert self.context is not None
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_UPDATE,))
        run = await self._require_run(run_id)
        if run.status in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
            raise AppError("任务仍在执行，不能重试失败题", code=40097, status_code=400)
        blocked = await self._resume_blocked_reason(run)
        if blocked:
            raise AppError(blocked, code=40982, status_code=409)
        other = await self.repo.find_active_run(run.experiment_id)
        if other is not None and other.id != run.id:
            raise AppError("该实验已有进行中的评测", code=40981, status_code=409)
        rows = await EvaluationRepository(self.session, run.tenant_id).list_results(run.id)
        for row in rows:
            if row.result_status != ResultCaseStatus.FAILED.value and not row.judge_error and not row.error_message:
                continue
            stages = dict(row.stages or {})
            if row.judge_error or (
                stage_status(stages, EvalStage.JUDGE.value) == StageStatus.FAILED.value and row.answer
            ):
                stages = mark_stage(stages, EvalStage.JUDGE.value, StageStatus.PENDING.value, error=None)
                row.judge_error = None
                side = dict(stage_entry(stages, EvalStage.GENERATE.value).get("generation_side") or {})
                row.generation_metrics = side or None
                row.judge_raw = None
            elif not stage_succeeded(stage_status(stages, EvalStage.GENERATE.value)):
                stages = mark_stage(stages, EvalStage.GENERATE.value, StageStatus.PENDING.value, error=None)
            row.stages = stages
            row.result_status = ResultCaseStatus.PENDING.value
            row.error_message = None
        run.status = RunStatus.QUEUED.value
        run.pause_requested = False
        run.cancel_requested = False
        run.finished_at = None
        run.error_message = None
        run.interrupt_reason = None
        run.attempt += 1
        await self.session.commit()
        if settings.task_executor == "redis":
            await enqueue_eval_run(run.id)
        await self.session.refresh(run)
        return run

    async def retry(self, run_id: int) -> EvaluationRun:
        """失败/取消后继续同一 Run：保留成功题，重试其余题目。"""
        return await self.retry_failed(run_id)

    async def execute(self, run_id: int) -> None:
        """领取租约后按 checkpoint 续跑。使用快照中的数据集与参数，不读实验当前配置。"""
        run = await self._acquire_lease(run_id)
        if run is None:
            return
        if run.cancel_requested:
            run.status = RunStatus.CANCELLED.value
            run.interrupt_reason = InterruptReason.CANCELLED.value
            run.finished_at = datetime.now(UTC)
            self._release_lease(run)
            await self.session.commit()
            return
        blocked = await self._resume_blocked_reason(run)
        if blocked:
            await self._pause_run(run, InterruptReason.SNAPSHOT_UNAVAILABLE.value, blocked)
            return
        if type(run.created_by) is not int or run.created_by <= 0:
            await self._fail_run(run, InterruptReason.FORBIDDEN.value, "评测缺少创建者，拒绝继续执行")
            return
        if type(run.tenant_id) is not int or run.tenant_id <= 0:
            await self._fail_run(run, InterruptReason.FORBIDDEN.value, "评测缺少租户，拒绝继续执行")
            return
        try:
            context = snapshot_store().load_for_principal(
                user_id=run.created_by,
                tenant_id=run.tenant_id,
            )
        except SecurityError as exc:
            reason, terminal = _auth_interrupt(exc)
            if terminal:
                await self._fail_run(run, reason, exc.message)
            else:
                await self._pause_run(run, reason, exc.message)
            return
        repo = EvaluationRepository(self.session, run.tenant_id)
        version = await repo.get_version(run.dataset_id, run.dataset_version)
        if version is None:
            await self._pause_run(run, InterruptReason.SNAPSHOT_UNAVAILABLE.value, "数据集快照不存在")
            return
        run.status = RunStatus.RUNNING.value
        run.pause_requested = False
        run.interrupt_reason = None
        run.error_message = None
        run.error_detail = None
        if run.started_at is None:
            run.started_at = datetime.now(UTC)
        await self.session.commit()

        config = dict(run.config_snapshot or {})
        cases = _filter_eval_cases(list((version.snapshot or {}).get("cases") or []), config)
        retrieval = RetrievalService(self.session, context)
        chat = ChatService(self.session, context)
        consecutive_judge_failures = 0
        try:
            for index, case in enumerate(cases, start=1):
                await self.session.refresh(run)
                if run.cancel_requested:
                    run.status = RunStatus.CANCELLED.value
                    run.interrupt_reason = InterruptReason.CANCELLED.value
                    run.finished_at = datetime.now(UTC)
                    self._release_lease(run)
                    await self.session.commit()
                    return
                if run.pause_requested:
                    await self._pause_run(run, InterruptReason.USER_PAUSE.value, run.error_message or "用户暂停")
                    return
                await self._sync_usage(run, repo)
                assert_budget(run, extra_tokens=estimate_next_call() if config.get("evaluate_generation") else 0)
                run.current_case_id = int(case["id"])
                run.current_stage = EvalStage.RETRIEVE.value
                self._heartbeat(run)
                await self.session.commit()
                existing = await repo.get_result_by_run_case(run.id, int(case["id"]))
                if existing is not None and existing.result_status == ResultCaseStatus.SUCCESS.value:
                    continue
                try:
                    result_row = await self._run_case_with_checkpoints(run, case, config, retrieval, chat, existing)
                except PauseRun as exc:
                    await self._pause_run(run, exc.reason, exc.message, diagnostics=exc.diagnostics)
                    return
                except AppError as exc:
                    if not await self._handle_case_error(run, case, existing, exc):
                        return
                    consecutive_judge_failures = 0
                    run.progress = int(index / max(len(cases), 1) * 100)
                    await self._sync_usage(run, repo)
                    await self.session.commit()
                    continue
                except Exception as exc:
                    logger.exception("evaluation case crashed run=%s case=%s", run.id, case.get("id"))
                    await self._save_case_failure(run, case, existing, "本题评测失败")
                    await self._pause_run(run, InterruptReason.WORKER_CRASH.value, "Worker 异常退出，已保存部分结果")
                    raise exc
                if result_row.judge_error:
                    consecutive_judge_failures += 1
                    if consecutive_judge_failures >= 3:
                        await self._pause_run(
                            run,
                            InterruptReason.CASE_FAILED.value,
                            "连续 3 题无法解析 Judge 结果，已暂停以免继续消耗 Token",
                        )
                        return
                else:
                    consecutive_judge_failures = 0
                run.progress = int(index / max(len(cases), 1) * 100)
                await self._sync_usage(run, repo)
                await self.session.commit()
            await self._finalize_success(run, repo, cases)
        except PauseRun as exc:
            await self._pause_run(run, exc.reason, exc.message, diagnostics=exc.diagnostics)

    async def _run_case_with_checkpoints(
        self,
        run: EvaluationRun,
        case: dict,
        config: dict,
        retrieval: RetrievalService,
        chat: ChatService,
        existing: EvaluationResult | None,
    ) -> EvaluationResult:
        """按阶段执行并立即提交。已成功阶段跳过，Judge 失败时复用已生成回答。"""
        row = existing or await self._insert_pending_result(run, case)
        stages = dict(row.stages or empty_stages()) if row.stages else empty_stages()
        k = int(config.get("top_k") or settings.default_top_k)
        started = datetime.now(UTC)

        if not self._retrieve_done(row, stages):
            run.current_stage = EvalStage.RETRIEVE.value
            await self.session.commit()
            search = await call_with_retry(
                lambda: retrieval.search(
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
                ),
                what="retrieve",
                stage=EvalStage.RETRIEVE.value,
                case_id=int(case["id"]),
            )
            context_budget = int(settings.chat_max_context_chars)
            row.retrieved = pack_retrieved_hits(search.hits, case, context_budget=context_budget)
            stages = mark_stage(
                stages,
                EvalStage.RETRIEVE.value,
                StageStatus.SUCCESS.value,
                latency_ms=search.latency_ms,
                extra={
                    "diagnostics": retrieval_diagnostics(
                        search, context_budget=context_budget, packed=row.retrieved
                    )
                },
            )
            if not config.get("rerank"):
                stages = mark_stage(stages, EvalStage.RERANK.value, StageStatus.SKIPPED.value)
            elif search.rerank_degraded:
                stages = mark_stage(stages, EvalStage.RERANK.value, StageStatus.DEGRADED.value)
            elif search.rerank_applied:
                stages = mark_stage(stages, EvalStage.RERANK.value, StageStatus.SUCCESS.value)
            else:
                stages = mark_stage(stages, EvalStage.RERANK.value, StageStatus.SKIPPED.value)
            row.latency_ms = search.latency_ms
            row.stages = stages
            row.usage = merge_embedding_usage(row.usage, _embedding_usage(search.stages))
            await self.session.commit()

        if not stage_succeeded(stage_status(stages, EvalStage.METRICS.value)) or row.retrieval_metrics is None:
            run.current_stage = EvalStage.METRICS.value
            row.retrieval_metrics = await _compute_metrics_async(
                self.session,
                case,
                row.retrieved or [],
                k,
                tenant_id=run.tenant_id,
                knowledge_base_ids=list(config.get("knowledge_base_ids") or []),
            )
            stages = mark_stage(stages, EvalStage.METRICS.value, StageStatus.SUCCESS.value)
            row.stages = stages
            await self.session.commit()

        if not config.get("evaluate_generation"):
            stages = mark_stage(stages, EvalStage.GENERATE.value, StageStatus.SKIPPED.value)
            stages = mark_stage(stages, EvalStage.JUDGE.value, StageStatus.SKIPPED.value)
            row.stages = stages
            row.result_status = ResultCaseStatus.SUCCESS.value
            row.error_message = None
            row.latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000) or row.latency_ms
            await self.session.commit()
            return row

        if not self._generate_done(row, stages):
            run.current_stage = EvalStage.GENERATE.value
            await self.session.commit()
            assert_budget(run, extra_tokens=estimate_next_call())
            hits = row.retrieved or []
            if not hits and case.get("is_unanswerable"):
                from app.services.chat import _REFUSE

                row.answer = _REFUSE
                side = await self._generation_side_metrics(run, case, hits, _REFUSE, config)
                row.generation_metrics = {
                    **side,
                    "faithfulness": 1.0,
                    "answer_relevancy": 1.0,
                    "answer_correctness": None,
                    "refused": True,
                    "judge_skipped": True,
                    "unanswerable_outcome": unanswerable_outcome(retrieved_nonempty=False, answer=_REFUSE),
                }
                stages = mark_stage(stages, EvalStage.GENERATE.value, StageStatus.SUCCESS.value)
                stages = mark_stage(stages, EvalStage.JUDGE.value, StageStatus.SKIPPED.value)
            else:
                started_gen = datetime.now(UTC)
                prompt_hits = _prompt_hit_objects(hits)
                trace = chat._build_messages(str(case["question"]), prompt_hits, [])
                assert_no_answer_leak(trace.messages, case.get("expected_answer"))
                answer, usage = await call_with_retry(
                    lambda: collect_chat(trace.messages),
                    what="generate",
                    stage=EvalStage.GENERATE.value,
                    case_id=int(case["id"]),
                )
                row.answer = answer
                generate_usage = _merge_usage({}, usage, estimated=usage is None or usage.get("prompt_tokens") is None)
                row.usage = _merge_usage(row.usage, usage, estimated=usage is None or usage.get("prompt_tokens") is None)
                side = await self._generation_side_metrics(run, case, hits, answer, config, trace=trace)
                gen_ms = int((datetime.now(UTC) - started_gen).total_seconds() * 1000)
                stages = mark_stage(
                    stages,
                    EvalStage.GENERATE.value,
                    StageStatus.SUCCESS.value,
                    latency_ms=gen_ms,
                    usage=generate_usage,
                    extra={
                        "citation_presence": citation_presence(row.answer, len(trace.prompt_chunk_ids)),
                        "prompt_chunk_ids": side.get("prompt_chunk_ids") or trace.prompt_chunk_ids,
                        "retrieved_chunk_ids": side.get("retrieved_chunk_ids") or trace.retrieved_chunk_ids,
                        "omitted_chunk_ids": side.get("omitted_chunk_ids"),
                        "prompt_truncated": side.get("prompt_truncated"),
                        "context_budget_limited": side.get("context_budget_limited"),
                        "truncation_reason": side.get("truncation_reason"),
                        "prompt_used_chars": side.get("budget_used_chars", trace.used_chars),
                        "budget_used_chars": side.get("budget_used_chars"),
                        "budget_limit_chars": side.get("budget_limit_chars"),
                        "omitted_chunk_count": side.get("omitted_chunk_count"),
                        "partially_truncated_chunk_count": side.get("partially_truncated_chunk_count"),
                        "citation": side.get("citation"),
                        "generation_side": side,
                    },
                )
            row.stages = stages
            await self._touch_run_usage(run)
            await self.session.commit()

        if stage_status(stages, EvalStage.JUDGE.value) != StageStatus.SKIPPED.value and not self._judge_done(row, stages):
            run.current_stage = EvalStage.JUDGE.value
            await self.session.commit()
            assert_budget(run, extra_tokens=estimate_next_call())
            contexts = generation_contexts(row.retrieved or [])
            started_judge = datetime.now(UTC)
            generation_metrics, judge_raw, judge_error = await call_with_retry(
                lambda: judge_answer(
                    question=str(case["question"]),
                    answer=row.answer or "",
                    contexts=contexts,
                    expected_answer=case.get("expected_answer"),
                    is_unanswerable=bool(case.get("is_unanswerable")),
                    is_false_premise=is_false_premise_case(case),
                ),
                what="judge",
                stage=EvalStage.JUDGE.value,
                case_id=int(case["id"]),
            )
            judge_usage = None
            if isinstance(judge_raw, dict) and isinstance(judge_raw.get("usage"), dict):
                judge_usage = judge_raw.get("usage")
                row.usage = _merge_usage(
                    row.usage,
                    judge_usage,
                    estimated=judge_usage.get("prompt_tokens") is None,
                )
            side = dict(stage_entry(stages, EvalStage.GENERATE.value).get("generation_side") or {})
            if not side:
                side = await self._generation_side_metrics(run, case, row.retrieved or [], row.answer or "", config)
            merged = dict(side)
            if generation_metrics:
                merged.update(generation_metrics)
            merged["is_unanswerable"] = bool(case.get("is_unanswerable"))
            merged["is_false_premise"] = is_false_premise_case(case)
            if case.get("is_unanswerable"):
                outcome = unanswerable_outcome(
                    retrieved_nonempty=bool(row.retrieved),
                    answer=row.answer,
                )
                merged["refusal_keyword_hint"] = outcome["refusal_keyword_hint"]
                merged["unanswerable_outcome"] = outcome
                merged.pop("refusal", None)
            if judge_error:
                merged["judge_error"] = judge_error
            row.generation_metrics = merged
            row.judge_raw = judge_raw
            row.judge_error = judge_error
            row.judge_model = str(config.get("chat_model") or settings.chat_model)
            row.judge_prompt_version = str(config.get("judge_prompt_version") or JUDGE_PROMPT_VERSION)
            judge_ms = int((datetime.now(UTC) - started_judge).total_seconds() * 1000)
            if judge_error:
                stages = mark_stage(
                    stages,
                    EvalStage.JUDGE.value,
                    StageStatus.FAILED.value,
                    latency_ms=judge_ms,
                    usage=judge_usage,
                    error=judge_error,
                )
                row.result_status = ResultCaseStatus.FAILED.value
                row.error_message = judge_error
            else:
                stages = mark_stage(
                    stages,
                    EvalStage.JUDGE.value,
                    StageStatus.SUCCESS.value,
                    latency_ms=judge_ms,
                    usage=judge_usage,
                )
                row.result_status = ResultCaseStatus.SUCCESS.value
                row.error_message = None
            row.stages = stages
            await self._touch_run_usage(run)
            await self.session.commit()
            return row

        row.stages = stages
        row.result_status = ResultCaseStatus.SUCCESS.value
        row.error_message = None
        await self.session.commit()
        return row

    def _retrieve_done(self, row: EvaluationResult, stages: dict) -> bool:
        if stage_succeeded(stage_status(stages, EvalStage.RETRIEVE.value)):
            return True
        return bool(row.retrieved) and not stages

    def _generate_done(self, row: EvaluationResult, stages: dict) -> bool:
        if stage_succeeded(stage_status(stages, EvalStage.GENERATE.value)):
            return True
        return bool(row.answer) and stage_status(stages, EvalStage.GENERATE.value) != StageStatus.FAILED.value

    def _judge_done(self, row: EvaluationResult, stages: dict) -> bool:
        status = stage_status(stages, EvalStage.JUDGE.value)
        if stage_succeeded(status):
            return True
        if row.judge_error:
            return False
        metrics = row.generation_metrics if isinstance(row.generation_metrics, dict) else {}
        return bool(metrics.get("judge_skipped") or metrics.get("faithfulness") is not None)

    async def _generation_side_metrics(
        self,
        run: EvaluationRun,
        case: dict,
        retrieved: list[dict],
        answer: str,
        config: dict,
        *,
        trace=None,
    ) -> dict:
        observability = prompt_observability(retrieved, trace)
        prompt_ids = list(observability["prompt_chunk_ids"]) or (
            list(trace.prompt_chunk_ids) if trace is not None else _prompt_chunk_ids(retrieved)
        )
        retrieved_ids = list(observability["retrieved_chunk_ids"]) or [
            int(item["chunk_id"]) for item in retrieved if item.get("chunk_id") is not None
        ]
        gold = gold_chunk_ids(case)
        valid: set[int] = set()
        rejected: dict[int, str] = {}
        spec = parse_case_evidence(case) if not case.get("is_unanswerable") else None
        if spec is not None:
            live = await _load_live_chunks(self.session, spec.all_chunk_ids())
            valid, rejected = classify_evidence_chunks(
                spec,
                judgments=list(case.get("judgments") or []),
                live_chunks=live,
                allowed_kb_ids={int(item) for item in (config.get("knowledge_base_ids") or [])},
                tenant_id=run.tenant_id,
            )
        citation = citation_metrics(
            answer,
            prompt_ids,
            gold_chunk_ids=gold,
            support_chunk_ids=support_chunk_ids(case, valid_chunk_ids=valid if spec is not None else None),
            is_unanswerable=bool(case.get("is_unanswerable")),
        )
        prompt_cov = prompt_evidence_coverage(
            prompt_ids,
            case,
            valid_chunk_ids=valid,
            rejected=rejected,
        )
        fabric = fabricated_terms(
            answer,
            absent_terms_from_case(case),
            question=str(case.get("question") or ""),
        )
        payload = {
            "generation_metric_version": GENERATION_METRIC_VERSION,
            "retrieved_chunk_ids": retrieved_ids,
            "prompt_chunk_ids": prompt_ids,
            "omitted_chunk_ids": observability["omitted_chunk_ids"],
            "omitted_chunk_count": observability["omitted_chunk_count"],
            "partially_truncated_chunk_count": observability["partially_truncated_chunk_count"],
            "truncation_reason": observability["truncation_reason"],
            "context_budget_limited": observability["context_budget_limited"],
            "budget_used_chars": observability["budget_used_chars"],
            "budget_limit_chars": observability["budget_limit_chars"],
            "prompt_truncated": observability["prompt_truncated"],
            "citation": citation,
            "citation_correctness": citation.get("citation_correctness"),
            "citation_validity": citation.get("citation_validity"),
            "gold_citation_match": citation.get("gold_citation_match"),
            "claim_support": citation.get("claim_support"),
            "claim_support_skipped": citation.get("claim_support_skipped"),
            "is_unanswerable": bool(case.get("is_unanswerable")),
            "is_false_premise": is_false_premise_case(case),
        }
        if case.get("is_unanswerable"):
            payload.update(fabric)
        payload.update(
            {
                key: prompt_cov[key]
                for key in (
                    "prompt_evidence_coverage_at_k",
                    "prompt_complete_evidence_at_k",
                    "prompt_evidence_coverage_skipped",
                    "uncovered_facts",
                    "required_facts",
                )
                if key in prompt_cov
            }
        )
        return payload

    async def _insert_pending_result(self, run: EvaluationRun, case: dict) -> EvaluationResult:
        repo = EvaluationRepository(self.session, run.tenant_id)
        row = EvaluationResult(
            tenant_id=run.tenant_id,
            run_id=run.id,
            case_id=int(case["id"]),
            question=str(case.get("question") or ""),
            is_unanswerable=bool(case.get("is_unanswerable")),
            retrieved=[],
            result_status=ResultCaseStatus.PENDING.value,
            stages=empty_stages(),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
            return row
        except IntegrityError:
            existed = await repo.get_result_by_run_case(run.id, int(case["id"]))
            if existed is None:
                raise
            return existed

    async def _handle_case_error(
        self, run: EvaluationRun, case: dict, existing: EvaluationResult | None, exc: AppError
    ) -> bool:
        """返回 False 表示已暂停或终止整个 Run。"""
        if exc.code in {40320, 40361, 40362, 40363, 40450}:
            await self._fail_run(run, InterruptReason.FORBIDDEN.value, exc.message)
            return False
        reason = interrupt_code_reason(exc)
        if exc.code in CONTEXT_OVERFLOW_CODES:
            await self._save_case_failure(run, case, existing, exc.message, stages_error=EvalStage.GENERATE.value)
            if not settings.eval_continue_on_error:
                await self._pause_run(run, InterruptReason.CONTEXT_OVERFLOW.value, exc.message)
                return False
            return True
        if reason in {
            InterruptReason.RATE_LIMIT.value,
            InterruptReason.TIMEOUT.value,
            InterruptReason.NETWORK.value,
            InterruptReason.INSUFFICIENT_FUNDS.value,
            InterruptReason.INVALID_KEY.value,
        }:
            await self._pause_run(
                run,
                reason,
                exc.message,
                diagnostics=interrupt_diagnostics(
                    exc,
                    stage=run.current_stage,
                    case_id=int(case["id"]),
                    attempts=1,
                ),
            )
            return False
        await self._save_case_failure(run, case, existing, exc.message)
        if not settings.eval_continue_on_error:
            await self._pause_run(run, InterruptReason.CASE_FAILED.value, exc.message)
            return False
        return True

    async def _save_case_failure(
        self,
        run: EvaluationRun,
        case: dict,
        existing: EvaluationResult | None,
        message: str,
        *,
        stages_error: str | None = None,
    ) -> None:
        row = existing or await self._insert_pending_result(run, case)
        stages = dict(row.stages or empty_stages())
        target = stages_error or run.current_stage or EvalStage.RETRIEVE.value
        row.stages = mark_stage(stages, target, StageStatus.FAILED.value, error=message)
        row.result_status = ResultCaseStatus.FAILED.value
        row.error_message = message
        await self.session.commit()

    async def _finalize_success(self, run: EvaluationRun, repo: EvaluationRepository, cases: list[dict]) -> None:
        rows = await repo.list_results(run.id)
        supervised: list[dict] = []
        unanswerable_stats: list[dict] = []
        gen_scores: list[dict] = []
        refuse_hits = 0
        unanswerable_total = 0
        failed = 0
        for result_row in rows:
            if result_row.result_status == ResultCaseStatus.FAILED.value:
                failed += 1
            if result_row.retrieval_metrics and not result_row.is_unanswerable:
                if "skipped" not in result_row.retrieval_metrics:
                    supervised.append(result_row.retrieval_metrics)
            if result_row.retrieval_metrics and result_row.is_unanswerable:
                unanswerable_stats.append(result_row.retrieval_metrics)
                unanswerable_total += 1
                if looks_like_refusal(result_row.answer or ""):
                    refuse_hits += 1
            if result_row.generation_metrics:
                payload = dict(result_row.generation_metrics)
                payload["is_unanswerable"] = bool(result_row.is_unanswerable)
                payload["judge_error"] = result_row.judge_error
                gen_scores.append(payload)
        metrics = aggregate_retrieval(supervised, unanswerable_rows=unanswerable_stats)
        if unanswerable_total:
            metrics["unanswerable_refuse_rate"] = refuse_hits / unanswerable_total
        if gen_scores:
            metrics["generation"] = aggregate_generation(gen_scores)
        summary = accumulate_results(rows)
        run.metrics = metrics
        run.usage = {
            "prompt_tokens": summary["prompt_tokens"],
            "completion_tokens": summary["completion_tokens"],
            "token_estimated": summary["token_estimated"],
            "latency_p50_ms": _percentile(summary["latencies"], 50),
            "latency_p95_ms": _percentile(summary["latencies"], 95),
            "estimated_cost_usd": summary["estimated_cost_usd"],
            "embedding_api_calls": summary["embedding_api_calls"],
            "embedding_cache_hits": summary["embedding_cache_hits"],
            "embedding_prompt_tokens": summary["embedding_prompt_tokens"],
            "embedding_tokens_missing": summary["embedding_tokens_missing"],
            "embedding_tokens_estimated": summary["embedding_tokens_estimated"],
            "case_count": len(cases),
            "completed_count": summary["completed_count"],
            "failed_count": summary["failed_count"] or failed,
            "pending_count": max(len(cases) - len(rows), 0),
        }
        run.progress = 100
        run.current_case_id = None
        run.current_stage = None
        run.interrupt_reason = None
        run.error_message = None
        run.error_detail = None
        run.status = RunStatus.SUCCESS.value
        run.finished_at = datetime.now(UTC)
        self._release_lease(run)
        await self.session.commit()

    async def _sync_usage(self, run: EvaluationRun, repo: EvaluationRepository) -> None:
        rows = await repo.list_results(run.id)
        summary = accumulate_results(rows)
        version_meta = run.dataset_snapshot_meta if isinstance(run.dataset_snapshot_meta, dict) else {}
        total = int(version_meta.get("ready_count") or len(rows))
        run.usage = {
            **(run.usage if isinstance(run.usage, dict) else {}),
            "prompt_tokens": summary["prompt_tokens"],
            "completion_tokens": summary["completion_tokens"],
            "token_estimated": summary["token_estimated"],
            "estimated_cost_usd": summary["estimated_cost_usd"],
            "embedding_api_calls": summary["embedding_api_calls"],
            "embedding_cache_hits": summary["embedding_cache_hits"],
            "embedding_prompt_tokens": summary["embedding_prompt_tokens"],
            "embedding_tokens_missing": summary["embedding_tokens_missing"],
            "embedding_tokens_estimated": summary["embedding_tokens_estimated"],
            "completed_count": summary["completed_count"],
            "failed_count": summary["failed_count"],
            "pending_count": max(total - summary["completed_count"] - summary["failed_count"], 0),
            "case_count": total,
        }

    async def _touch_run_usage(self, run: EvaluationRun) -> None:
        repo = EvaluationRepository(self.session, run.tenant_id)
        await self._sync_usage(run, repo)

    async def _pause_run(
        self,
        run: EvaluationRun,
        reason: str,
        message: str,
        diagnostics: dict | None = None,
    ) -> None:
        run.status = RunStatus.PAUSED.value
        run.interrupt_reason = reason
        run.error_message = message
        if diagnostics is not None:
            run.error_detail = diagnostics
        elif reason == InterruptReason.USER_PAUSE.value:
            run.error_detail = None
        run.pause_requested = False
        self._release_lease(run)
        await self._note_pending_error(run, message, diagnostics)
        await self.session.commit()

    async def _fail_run(self, run: EvaluationRun, reason: str, message: str) -> None:
        """确定性授权失败。终止本次 Run，不进入可自动恢复的暂停。"""
        run.status = RunStatus.FAILED.value
        run.interrupt_reason = reason
        run.error_message = message
        run.finished_at = datetime.now(UTC)
        run.pause_requested = False
        self._release_lease(run)
        await self.session.commit()

    async def _note_pending_error(self, run: EvaluationRun, message: str, diagnostics: dict | None) -> None:
        """把失败说明写到未完成题目上，但不把阶段标成成功，恢复时仍会重试。"""
        if run.current_case_id is None:
            return
        repo = EvaluationRepository(self.session, run.tenant_id)
        row = await repo.get_result_by_run_case(run.id, int(run.current_case_id))
        if row is None or row.result_status == ResultCaseStatus.SUCCESS.value:
            return
        stage_name = run.current_stage or EvalStage.RETRIEVE.value
        stages = dict(row.stages or empty_stages())
        current = dict(stage_entry(stages, stage_name))
        if stage_succeeded(str(current.get("status") or "")):
            return
        current["error"] = message
        if diagnostics is not None:
            current["diagnostics"] = diagnostics
        stages[stage_name] = current
        row.stages = stages

    async def _acquire_lease(self, run_id: int) -> EvaluationRun | None:
        """同一 Run 同时只允许一个 Worker。租约过期后可被其他进程收回。"""
        now = datetime.now(UTC)
        until = now + timedelta(seconds=max(15, settings.eval_lease_seconds))
        filters = [
            EvaluationRun.id == run_id,
            EvaluationRun.status.in_(
                (RunStatus.QUEUED.value, RunStatus.PAUSED.value, RunStatus.RUNNING.value)
            ),
            or_(
                EvaluationRun.lease_until.is_(None),
                EvaluationRun.lease_until <= now,
                EvaluationRun.lease_owner == self.lease_owner,
            ),
        ]
        sync = getattr(self.session, "sync_session", None)
        bound = getattr(sync, "tenant_id", None)
        if type(bound) is int and bound > 0:
            filters.append(EvaluationRun.tenant_id == bound)
        stmt = update(EvaluationRun).where(*filters).values(lease_owner=self.lease_owner, lease_until=until)
        result = await self.session.execute(stmt)
        await self.session.commit()
        if int(getattr(result, "rowcount", 0) or 0) == 0:
            return None
        return await _load_run(self.session, run_id)

    def _heartbeat(self, run: EvaluationRun) -> None:
        run.lease_owner = self.lease_owner
        run.lease_until = datetime.now(UTC) + timedelta(seconds=max(15, settings.eval_lease_seconds))

    def _release_lease(self, run: EvaluationRun) -> None:
        run.lease_owner = None
        run.lease_until = None

    async def _resume_blocked_reason(self, run: EvaluationRun) -> str | None:
        """快照中的数据集、知识库、Embedding 与当前运行时不一致时禁止悄悄换索引。"""
        snap = run.config_snapshot if isinstance(run.config_snapshot, dict) else {}
        runtime = default_experiment_config()
        if snap.get("embedding_model") and snap.get("embedding_model") != settings.embedding_model:
            return (
                f"Embedding 已从 {snap.get('embedding_model')} 变为 {settings.embedding_model}，"
                "不能用原快照恢复"
            )
        dims = snap.get("embedding_dimensions")
        if dims is not None and int(dims) != int(settings.embedding_dimensions):
            return "Embedding 维度已变化，原索引不可用"
        if snap.get("evaluate_generation"):
            if snap.get("chat_model") and snap.get("chat_model") != runtime.get("chat_model"):
                return (
                    f"Chat 模型已从 {snap.get('chat_model')} 变为 {runtime.get('chat_model')}，"
                    "不能悄悄切换配置"
                )
            if snap.get("prompt_version") and snap.get("prompt_version") != runtime.get("prompt_version"):
                return "Prompt 版本已变化，不能用原快照恢复"
        if snap.get("rerank") and snap.get("rerank_model") and snap.get("rerank_model") != runtime.get("rerank_model"):
            return "Rerank 模型已变化，不能用原快照恢复"
        repo = EvaluationRepository(self.session, run.tenant_id)
        if await repo.get_version(run.dataset_id, run.dataset_version) is None:
            return "数据集快照不存在"
        bases = KnowledgeBaseRepository(self.session, run.tenant_id)
        for item in snap.get("knowledge_base_ids") or []:
            if await bases.get_in_tenant(int(item)) is None:
                return f"知识库 {item} 不可用，不能恢复"
        return None

    async def _require_run(self, run_id: int) -> EvaluationRun:
        run = await self.repo.get_run(run_id)
        if run is None:
            raise AppError("评测任务不存在或不可访问", code=40483, status_code=404)
        return run

    async def probe(self, case_id: int, payload) -> ProbeOut:
        """单题真实检索评测。不创建实验 run，不改线上索引。"""
        assert self.context is not None
        self.auth.require_all(self.context, (PermissionCode.KNOWLEDGE_READ,))
        case = await self.repo.get_case(case_id)
        if case is None:
            raise AppError("评测问题不存在或不可访问", code=40481, status_code=404)
        judgments = await self.repo.list_judgments(case.id)
        dataset = await self.repo.get_dataset(case.dataset_id)
        snapshot_case = {
            "id": case.id,
            "question": case.question,
            "expected_answer": case.expected_answer,
            "is_unanswerable": case.is_unanswerable,
            "judgments": [
                {
                    "chunk_id": item.chunk_id,
                    "document_id": item.document_id,
                    "filename": item.filename if hasattr(item, "filename") else "",
                    "relevance": item.relevance,
                    "stale": item.stale,
                }
                for item in judgments
            ],
        }
        config = {
            "strategy": payload.strategy,
            "top_k": payload.top_k,
            "rerank": payload.rerank,
            "evaluate_generation": payload.generate,
            "knowledge_base_ids": payload.knowledge_base_ids
            or list((dataset.knowledge_base_ids if dataset else None) or []),
        }
        retrieval = RetrievalService(self.session, self.context)
        chat = ChatService(self.session, self.context)

        class _Dummy:
            tenant_id = self.context.tenant_id
            id = 0

        dummy = _Dummy()
        result, usage = await self._evaluate_case(dummy, snapshot_case, config, retrieval, chat)  # type: ignore[arg-type]
        search = await retrieval.search(
            case.question,
            knowledge_base_ids=config["knowledge_base_ids"],
            strategy=config["strategy"],
            top_k=config["top_k"],
            rerank=config["rerank"],
            persist_log=True,
        )
        return ProbeOut(
            case_id=case.id,
            question=case.question,
            expected_answer=case.expected_answer,
            is_unanswerable=case.is_unanswerable,
            strategy=search.strategy,
            rerank_applied=search.rerank_applied,
            rerank_degraded=search.rerank_degraded,
            latency_ms=search.latency_ms,
            stages=search.stages,
            retrieved=result.retrieved or [],
            retrieval_metrics=result.retrieval_metrics,
            answer=result.answer,
            citations=[
                {
                    "chunk_id": hit.chunk_id,
                    "document_id": hit.document_id,
                    "filename": hit.filename,
                    "final_rank": hit.final_rank,
                }
                for hit in search.hits
            ],
            usage=usage,
            needs_human_review=bool(case.needs_human_review),
        )

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
        metrics = await _compute_metrics_async(
            self.session,
            case,
            _hits_to_retrieved(search.hits, case),
            k,
            tenant_id=run.tenant_id,
            knowledge_base_ids=list(config.get("knowledge_base_ids") or []),
        )
        retrieved = _hits_to_retrieved(search.hits, case)
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
                    "refused": True,
                    "judge_skipped": True,
                }
            else:
                trace = chat._build_messages(str(case["question"]), search.hits, [])
                assert_no_answer_leak(trace.messages, case.get("expected_answer"))
                answer, usage = await collect_chat(trace.messages)
                generation_metrics, judge_raw, judge_error = await judge_answer(
                    question=str(case["question"]),
                    answer=answer,
                    contexts=[hit.content for hit in search.hits[: len(trace.prompt_chunk_ids)]],
                    expected_answer=case.get("expected_answer"),
                    is_unanswerable=bool(case.get("is_unanswerable")),
                    is_false_premise=is_false_premise_case(case),
                )
                if generation_metrics is not None and case.get("is_unanswerable"):
                    generation_metrics["refusal_keyword_hint"] = looks_like_refusal(answer)
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
                result_status=ResultCaseStatus.SUCCESS.value,
                stages=empty_stages(),
            ),
            usage,
        )


async def _load_run(session: AsyncSession, run_id: int) -> EvaluationRun | None:
    return await session.scalar(select(EvaluationRun).where(EvaluationRun.id == run_id))


def _filter_eval_cases(cases: list[dict], config: dict) -> list[dict]:
    """正式评测只用冻结快照里的 READY 题；case_ids 用于烟测子集。"""
    ready = [item for item in cases if item.get("annotation_status") == AnnotationStatus.READY.value]
    raw_ids = config.get("case_ids")
    if raw_ids is None:
        return ready
    if not raw_ids:
        raise AppError("case_ids 为空，无法评测", code=40086, status_code=400)
    wanted = [int(item) for item in raw_ids]
    ready_by_id = {int(item["id"]): item for item in ready}
    missing = [case_id for case_id in wanted if case_id not in ready_by_id]
    if missing:
        raise AppError(
            f"case_ids 中有 {len(missing)} 道不在冻结 READY 快照中，例如 {missing[0]}",
            code=40086,
            status_code=400,
        )
    return [ready_by_id[case_id] for case_id in wanted]


def _prompt_chunk_ids(retrieved: list[dict]) -> list[int]:
    ids: list[int] = []
    for item in retrieved:
        if not isinstance(item, dict) or item.get("chunk_id") is None:
            continue
        if item.get("in_prompt") is False:
            continue
        if item.get("in_prompt") is None and not generation_text(item):
            continue
        ids.append(int(item["chunk_id"]))
    return ids


def _prompt_hit_objects(retrieved: list[dict]) -> list[RetrievedHit]:
    selected = []
    for item in retrieved:
        if not isinstance(item, dict):
            continue
        if item.get("in_prompt") is False:
            continue
        if item.get("in_prompt") is None and not generation_text(item):
            continue
        selected.append(item)
    return _hits_as_objects(selected)


def _hits_to_retrieved(hits, case: dict) -> list[dict]:
    """兼容 probe：展示摘要与生成摘录分开，预算与 Chat 上下文一致。"""
    return pack_retrieved_hits(hits, case, context_budget=int(settings.chat_max_context_chars))


def _hits_as_objects(hits: list[dict]) -> list[RetrievedHit]:
    return [
        RetrievedHit(
            chunk_id=int(item["chunk_id"]) if item.get("chunk_id") is not None else 0,
            document_id=int(item["document_id"]) if item.get("document_id") is not None else 0,
            knowledge_base_id=int(item.get("knowledge_base_id") or 0),
            filename=str(item.get("filename") or ""),
            content=generation_text(item),
            page_no=item.get("page_no"),
            heading=item.get("heading"),
            chunk_index=int(item.get("chunk_index") or 0),
            version=int(item.get("version") or 0),
            final_rank=int(item.get("final_rank") or 0),
        )
        for item in hits
    ]


def _compute_metrics(case: dict, retrieved: list[dict], k: int, *, coverage: dict | None = None) -> dict:
    ranked = [int(item["chunk_id"]) for item in retrieved if item.get("chunk_id") is not None]
    labeled = [
        LabeledItem(item_id=int(item["chunk_id"]), relevance=int(item["relevance"]))
        for item in case.get("judgments") or []
        if not item.get("stale")
    ]
    if case.get("is_unanswerable"):
        return unanswerable_retrieval_stats(ranked, k)
    if any(item.relevance >= 1 for item in labeled):
        metrics = retrieval_metrics(ranked, labeled, k=k, granularity="chunk")
        doc_ranked = _unique([int(item["document_id"]) for item in retrieved if item.get("document_id") is not None])
        doc_labeled = _document_labels(case.get("judgments") or [])
        if any(item.relevance >= 1 for item in doc_labeled):
            metrics["document"] = retrieval_metrics(doc_ranked, doc_labeled, k=k, granularity="document")
    else:
        metrics = {"skipped": "no_relevant_labels", "granularity": "chunk"}
    if coverage:
        for key, value in coverage.items():
            if key == "k":
                continue
            metrics[key] = value
    return metrics


async def _load_live_chunks(session: AsyncSession, chunk_ids: set[int]) -> dict[int, LiveChunk]:
    if not chunk_ids:
        return {}
    rows = (await session.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids)))).all()
    return {
        row.id: LiveChunk(
            chunk_id=row.id,
            tenant_id=row.tenant_id,
            knowledge_base_id=row.knowledge_base_id,
            status=row.status,
            enabled=bool(row.enabled),
        )
        for row in rows
    }


async def _compute_metrics_async(
    session: AsyncSession,
    case: dict,
    retrieved: list[dict],
    k: int,
    *,
    tenant_id: int | None,
    knowledge_base_ids: list[int],
) -> dict:
    coverage = None
    if not case.get("is_unanswerable"):
        ranked = [int(item["chunk_id"]) for item in retrieved if item.get("chunk_id") is not None]
        spec = parse_case_evidence(case)
        if spec is None:
            coverage = evidence_coverage_metrics(ranked, None, k=k, valid_chunk_ids=set())
        else:
            live = await _load_live_chunks(session, spec.all_chunk_ids())
            valid, rejected = classify_evidence_chunks(
                spec,
                judgments=list(case.get("judgments") or []),
                live_chunks=live,
                allowed_kb_ids={int(item) for item in knowledge_base_ids},
                tenant_id=tenant_id,
            )
            coverage = evidence_coverage_metrics(
                ranked,
                spec,
                k=k,
                valid_chunk_ids=valid,
                rejected=rejected,
            )
    return _compute_metrics(case, retrieved, k, coverage=coverage)


def _merge_usage(current: dict | None, incoming: dict | None, *, estimated: bool) -> dict:
    base = dict(current or {})
    prompt, completion, already = tokens_of(incoming)
    extra_p, extra_c, _ = tokens_of(base)
    merged = {
        "prompt_tokens": extra_p + prompt,
        "completion_tokens": extra_c + completion,
        "token_estimated": already or estimated or bool(base.get("token_estimated")),
    }
    merged["estimated_cost_usd"] = cost_of(merged["prompt_tokens"], merged["completion_tokens"])
    return merged


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


def _embedding_usage(stages: dict | None) -> dict:
    payload = stages if isinstance(stages, dict) else {}
    tokens = payload.get("embedding_prompt_tokens")
    return {
        "embedding_api_calls": int(payload.get("embedding_api_calls") or 0),
        "embedding_cache_hits": int(payload.get("embedding_cache_hits") or 0),
        "embedding_prompt_tokens": None if tokens is None else int(tokens),
        "embedding_tokens_estimated": bool(payload.get("embedding_tokens_estimated")),
    }


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float | None:
    """兼容使用统计：委托 budget.cost_of。"""
    return cost_of(prompt_tokens, completion_tokens)


def _percentile(values: list[int], pct: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return float(ordered[index])
