from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile
from fastapi.responses import PlainTextResponse

from app.api.deps import (
    DbSession,
    KnowledgeCreateContext,
    KnowledgeDeleteContext,
    KnowledgeReadContext,
    KnowledgeUpdateContext,
)
from app.core.config import settings
from app.models.evaluation import EvaluationResult, EvaluationRun
from app.repositories.evaluation import EvaluationRepository
from app.schemas.common import ApiResponse, ok
from app.schemas.evaluation import (
    CaseCreateIn,
    CaseDiagnosisOut,
    CaseListOut,
    CaseOut,
    CaseUpdateIn,
    CaseUpsertBatchIn,
    CaseUpsertResultOut,
    ChatImportIn,
    CompareOut,
    DatasetCreateIn,
    DatasetListOut,
    DatasetOut,
    DatasetUpdateIn,
    DatasetVersionDetailOut,
    DatasetVersionDiffOut,
    DatasetVersionListOut,
    ExperimentCreateIn,
    ExperimentListOut,
    ExperimentOut,
    ExperimentUpdateIn,
    FreezeOut,
    HumanOverrideIn,
    ImportResultOut,
    JudgmentIn,
    ResultOut,
    RunListOut,
    RunOut,
    RunResumeIn,
    SuggestionConfirmIn,
    SuggestionRejectIn,
    SuggestionUpdateIn,
    SuggestLabelsIn,
)
from app.schemas.ops import ProbeIn, ProbeOut
from app.services.evaluation import EvaluationService
from app.services.evaluation_run import EvaluationRunService, execute_eval_run
from app.services.label_suggestion import LabelSuggestionService, execute_label_job

router = APIRouter(tags=["knowledge-evaluation"])


def _schedule_eval_run(background: BackgroundTasks, run_id: int) -> None:
    """redis 已在 Service 入队；inline 等 HTTP 响应发出后再跑，避免运行接口一直 pending。"""
    if settings.task_executor == "redis":
        return
    background.add_task(execute_eval_run, run_id)


def _run_out(row: EvaluationRun) -> RunOut:
    return EvaluationService._run_out(row)


def _result_out(item: EvaluationResult, expected_answer: str | None = None) -> ResultOut:
    return ResultOut(
        id=item.id,
        run_id=item.run_id,
        case_id=item.case_id,
        question=item.question,
        expected_answer=expected_answer,
        is_unanswerable=item.is_unanswerable,
        retrieved=list(item.retrieved or []),
        retrieval_metrics=item.retrieval_metrics,
        answer=item.answer,
        generation_metrics=item.generation_metrics,
        judge_error=item.judge_error,
        human_override=item.human_override,
        latency_ms=item.latency_ms,
        usage=item.usage,
        error_message=item.error_message,
        result_status=getattr(item, "result_status", None) or "SUCCESS",
        stages=dict(getattr(item, "stages", None) or {}),
    )


@router.get("/evaluation/datasets", response_model=ApiResponse[DatasetListOut])
async def list_datasets(
    context: KnowledgeReadContext,
    session: DbSession,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[DatasetListOut]:
    return ok(await EvaluationService(session, context).list_datasets(q, page, page_size))


@router.post("/evaluation/datasets", response_model=ApiResponse[DatasetOut])
async def create_dataset(
    payload: DatasetCreateIn,
    context: KnowledgeCreateContext,
    session: DbSession,
) -> ApiResponse[DatasetOut]:
    return ok(await EvaluationService(session, context).create_dataset(payload), "已创建数据集")


@router.get("/evaluation/datasets/{dataset_id}", response_model=ApiResponse[DatasetOut])
async def get_dataset(dataset_id: int, context: KnowledgeReadContext, session: DbSession) -> ApiResponse[DatasetOut]:
    return ok(await EvaluationService(session, context).get_dataset(dataset_id))


@router.patch("/evaluation/datasets/{dataset_id}", response_model=ApiResponse[DatasetOut])
async def update_dataset(
    dataset_id: int,
    payload: DatasetUpdateIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[DatasetOut]:
    return ok(await EvaluationService(session, context).update_dataset(dataset_id, payload))


@router.delete("/evaluation/datasets/{dataset_id}", response_model=ApiResponse[None])
async def delete_dataset(dataset_id: int, context: KnowledgeDeleteContext, session: DbSession) -> ApiResponse[None]:
    await EvaluationService(session, context).delete_dataset(dataset_id)
    return ok(None, "已删除")


@router.post("/evaluation/datasets/{dataset_id}/copy", response_model=ApiResponse[DatasetOut])
async def copy_dataset(dataset_id: int, context: KnowledgeCreateContext, session: DbSession) -> ApiResponse[DatasetOut]:
    return ok(await EvaluationService(session, context).copy_dataset(dataset_id), "已复制")


@router.post("/evaluation/datasets/{dataset_id}/refresh-stale", response_model=ApiResponse[DatasetOut])
async def refresh_stale(dataset_id: int, context: KnowledgeUpdateContext, session: DbSession) -> ApiResponse[DatasetOut]:
    return ok(await EvaluationService(session, context).refresh_stale(dataset_id), "已刷新失效标注")


@router.post("/evaluation/datasets/{dataset_id}/freeze", response_model=ApiResponse[FreezeOut])
async def freeze_dataset(dataset_id: int, context: KnowledgeUpdateContext, session: DbSession) -> ApiResponse[FreezeOut]:
    row = await EvaluationService(session, context).freeze_version(dataset_id)
    return ok(
        FreezeOut(
            version=row.version,
            case_count=row.case_count,
            ready_count=row.ready_count,
            unanswerable_count=row.unanswerable_count,
            stale_judgment_count=row.stale_judgment_count,
        ),
        f"已创建冻结快照 v{row.version}",
    )


@router.get("/evaluation/datasets/{dataset_id}/versions", response_model=ApiResponse[DatasetVersionListOut])
async def list_dataset_versions(
    dataset_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[DatasetVersionListOut]:
    return ok(await EvaluationService(session, context).list_versions(dataset_id, page=page, page_size=page_size))


@router.get("/evaluation/datasets/{dataset_id}/versions/compare", response_model=ApiResponse[DatasetVersionDiffOut])
async def compare_dataset_versions(
    dataset_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
    left: int = Query(ge=1, description="对照版本"),
    right: int = Query(ge=1, description="待比较版本"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[DatasetVersionDiffOut]:
    return ok(
        await EvaluationService(session, context).compare_versions(
            dataset_id,
            left=left,
            right=right,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/evaluation/datasets/{dataset_id}/versions/{version}", response_model=ApiResponse[DatasetVersionDetailOut])
async def get_dataset_version(
    dataset_id: int,
    version: int,
    context: KnowledgeReadContext,
    session: DbSession,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[DatasetVersionDetailOut]:
    return ok(
        await EvaluationService(session, context).get_version_detail(
            dataset_id,
            version,
            page=page,
            page_size=page_size,
            q=q,
        )
    )


@router.delete("/evaluation/datasets/{dataset_id}/versions/{version}", response_model=ApiResponse[None])
async def delete_dataset_version(
    dataset_id: int,
    version: int,
    context: KnowledgeDeleteContext,
    session: DbSession,
) -> ApiResponse[None]:
    await EvaluationService(session, context).delete_version(dataset_id, version)
    return ok(None, "已删除未被引用的历史快照")


@router.get("/evaluation/datasets/{dataset_id}/cases", response_model=ApiResponse[CaseListOut])
async def list_cases(
    dataset_id: int,
    context: KnowledgeReadContext,
    session: DbSession,
    status: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[CaseListOut]:
    return ok(await EvaluationService(session, context).list_cases(dataset_id, status=status, q=q, page=page, page_size=page_size))


@router.post("/evaluation/datasets/{dataset_id}/cases", response_model=ApiResponse[CaseOut])
async def create_case(
    dataset_id: int,
    payload: CaseCreateIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[CaseOut]:
    return ok(await EvaluationService(session, context).create_case(dataset_id, payload), "已新增问题")


@router.post(
    "/evaluation/datasets/{dataset_id}/upsert-cases",
    response_model=ApiResponse[CaseUpsertResultOut],
    summary="按 external_key 幂等导入问题",
)
async def upsert_cases(
    dataset_id: int,
    payload: CaseUpsertBatchIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[CaseUpsertResultOut]:
    return ok(await EvaluationService(session, context).upsert_cases(dataset_id, payload), "已幂等写入")


@router.patch("/evaluation/cases/{case_id}", response_model=ApiResponse[CaseOut])
async def update_case(
    case_id: int,
    payload: CaseUpdateIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[CaseOut]:
    return ok(await EvaluationService(session, context).update_case(case_id, payload))


@router.delete("/evaluation/cases/{case_id}", response_model=ApiResponse[None])
async def delete_case(case_id: int, context: KnowledgeDeleteContext, session: DbSession) -> ApiResponse[None]:
    await EvaluationService(session, context).delete_case(case_id)
    return ok(None, "已删除问题")


@router.put("/evaluation/cases/{case_id}/judgments", response_model=ApiResponse[CaseOut])
async def replace_judgments(
    case_id: int,
    payload: list[JudgmentIn],
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[CaseOut]:
    return ok(await EvaluationService(session, context).replace_judgments(case_id, payload), "已保存标注")


@router.get("/evaluation/datasets/{dataset_id}/label-suggestions/estimate")
async def estimate_label_suggestions(
    dataset_id: int,
    session: DbSession,
    context: KnowledgeReadContext,
    rerun: bool = False,
    only_failed: bool = False,
) -> ApiResponse[dict]:
    data = await LabelSuggestionService(session, context).estimate(
        dataset_id,
        rerun=rerun,
        only_failed=only_failed,
    )
    return ok(data)


@router.get("/evaluation/datasets/{dataset_id}/label-suggestions")
async def list_label_suggestions(
    dataset_id: int,
    session: DbSession,
    context: KnowledgeReadContext,
    confidence: str | None = None,
    status: str | None = None,
) -> ApiResponse[list[dict]]:
    data = await LabelSuggestionService(session, context).list_suggestions(
        dataset_id,
        confidence=confidence,
        status=status,
    )
    return ok(data)


@router.get("/evaluation/datasets/{dataset_id}/label-jobs/current")
async def current_label_job(
    dataset_id: int,
    session: DbSession,
    context: KnowledgeReadContext,
) -> ApiResponse[dict | None]:
    data = await LabelSuggestionService(session, context).current_job(dataset_id)
    return ok(data)


@router.post("/evaluation/datasets/{dataset_id}/label-suggestions")
async def suggest_labels(
    dataset_id: int,
    payload: SuggestLabelsIn,
    session: DbSession,
    context: KnowledgeUpdateContext,
    background: BackgroundTasks,
) -> ApiResponse[dict]:
    service = LabelSuggestionService(session, context)
    if not payload.execute:
        return ok(
            await service.estimate(
                dataset_id,
                rerun=payload.rerun,
                only_failed=payload.only_failed,
                only_rejected=payload.only_rejected,
            )
        )
    data = await service.accept(
        dataset_id,
        rerun=payload.rerun,
        only_failed=payload.only_failed,
        only_rejected=payload.only_rejected,
    )
    if data["status"] == "QUEUED" and not data["already_running"]:
        background.add_task(execute_label_job, int(data["id"]))
    return ok(data, "已开始初标")


@router.post("/evaluation/datasets/{dataset_id}/label-suggestions/confirm")
async def confirm_label_suggestions(
    dataset_id: int,
    payload: SuggestionConfirmIn,
    session: DbSession,
    context: KnowledgeUpdateContext,
) -> ApiResponse[dict]:
    data = await LabelSuggestionService(session, context).confirm(dataset_id, payload)
    return ok(data)


@router.patch("/evaluation/label-suggestions/{suggestion_id}")
async def update_label_suggestion(
    suggestion_id: int,
    payload: SuggestionUpdateIn,
    session: DbSession,
    context: KnowledgeUpdateContext,
) -> ApiResponse[dict]:
    data = await LabelSuggestionService(session, context).update_draft(suggestion_id, payload)
    return ok(data)


@router.post("/evaluation/label-suggestions/{suggestion_id}/reject")
async def reject_label_suggestion(
    suggestion_id: int,
    payload: SuggestionRejectIn,
    session: DbSession,
    context: KnowledgeUpdateContext,
) -> ApiResponse[dict]:
    data = await LabelSuggestionService(session, context).reject(suggestion_id, payload.note)
    return ok(data)


@router.delete("/evaluation/label-suggestions/{suggestion_id}")
async def delete_label_suggestion(
    suggestion_id: int,
    session: DbSession,
    context: KnowledgeUpdateContext,
) -> ApiResponse[None]:
    await LabelSuggestionService(session, context).delete_suggestion(suggestion_id)
    return ok(None, "已删除初标草稿")


@router.post("/evaluation/cases/{case_id}/probe", summary="单题真实检索评测")
async def probe_case(
    case_id: int,
    payload: ProbeIn,
    context: KnowledgeReadContext,
    session: DbSession,
) -> ApiResponse[ProbeOut]:
    return ok(await EvaluationRunService(session, context).probe(case_id, payload))


@router.post("/evaluation/datasets/{dataset_id}/import", response_model=ApiResponse[ImportResultOut])
async def import_cases(
    dataset_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
    file: Annotated[UploadFile, File()],
) -> ApiResponse[ImportResultOut]:
    payload = await file.read()
    return ok(
        await EvaluationService(session, context).import_cases(dataset_id, file.filename or "import.csv", payload),
        "导入完成",
    )


@router.get("/evaluation/datasets/{dataset_id}/export")
async def export_cases(dataset_id: int, context: KnowledgeReadContext, session: DbSession) -> PlainTextResponse:
    content = await EvaluationService(session, context).export_cases(dataset_id)
    return PlainTextResponse(content, media_type="text/csv; charset=utf-8")


@router.post("/evaluation/datasets/{dataset_id}/from-chat")
async def import_from_chat(
    dataset_id: int,
    payload: ChatImportIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
):
    return ok(await EvaluationService(session, context).import_from_chat(dataset_id, payload))


@router.get("/evaluation/experiments", response_model=ApiResponse[ExperimentListOut])
async def list_experiments(
    context: KnowledgeReadContext,
    session: DbSession,
    dataset_id: int | None = None,
    strategy: str | None = Query(default=None, description="实验参数方案中的检索策略"),
    sort_by: str = Query(default="id", description="id / created_at"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[ExperimentListOut]:
    return ok(
        await EvaluationService(session, context).list_experiments(
            dataset_id,
            page,
            page_size,
            strategy=strategy.upper() if strategy else None,
            sort_by=sort_by,
            sort_order=sort_order.lower(),
        )
    )


@router.post("/evaluation/experiments", response_model=ApiResponse[ExperimentOut])
async def create_experiment(
    payload: ExperimentCreateIn,
    context: KnowledgeCreateContext,
    session: DbSession,
) -> ApiResponse[ExperimentOut]:
    return ok(await EvaluationService(session, context).create_experiment(payload), "已创建实验")


@router.get("/evaluation/experiments/{experiment_id}", response_model=ApiResponse[ExperimentOut])
async def get_experiment(
    experiment_id: int, context: KnowledgeReadContext, session: DbSession
) -> ApiResponse[ExperimentOut]:
    return ok(await EvaluationService(session, context).get_experiment(experiment_id))


@router.patch("/evaluation/experiments/{experiment_id}", response_model=ApiResponse[ExperimentOut])
async def update_experiment(
    experiment_id: int,
    payload: ExperimentUpdateIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[ExperimentOut]:
    return ok(await EvaluationService(session, context).update_experiment(experiment_id, payload))


@router.post("/evaluation/experiments/{experiment_id}/copy", response_model=ApiResponse[ExperimentOut])
async def copy_experiment(
    experiment_id: int, context: KnowledgeCreateContext, session: DbSession
) -> ApiResponse[ExperimentOut]:
    return ok(await EvaluationService(session, context).copy_experiment(experiment_id), "已复制实验")


@router.delete("/evaluation/experiments/{experiment_id}", response_model=ApiResponse[None])
async def delete_experiment(
    experiment_id: int, context: KnowledgeDeleteContext, session: DbSession
) -> ApiResponse[None]:
    await EvaluationService(session, context).delete_experiment(experiment_id)
    return ok(None, "已删除实验")


@router.post("/evaluation/experiments/{experiment_id}/run", response_model=ApiResponse[RunOut])
async def start_run(
    experiment_id: int,
    context: KnowledgeCreateContext,
    session: DbSession,
    background: BackgroundTasks,
) -> ApiResponse[RunOut]:
    row = await EvaluationRunService(session, context).start(experiment_id)
    _schedule_eval_run(background, row.id)
    return ok(_run_out(row), "已排队评测")


@router.get("/evaluation/runs", response_model=ApiResponse[RunListOut])
async def list_runs(
    context: KnowledgeReadContext,
    session: DbSession,
    experiment_id: int | None = None,
    status: str | None = Query(default=None, description="运行状态"),
    strategy: str | None = Query(default=None, description="config_snapshot 中的检索策略"),
    sort_by: str = Query(
        default="created_at",
        description="id / created_at / recall / mrr / ndcg / hit_rate / latency_p95",
    ),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[RunListOut]:
    return ok(
        await EvaluationService(session, context).list_runs(
            experiment_id=experiment_id,
            status=status.upper() if status else None,
            strategy=strategy.upper() if strategy else None,
            sort_by=sort_by,
            sort_order=sort_order.lower(),
            page=page,
            page_size=page_size,
        )
    )


@router.get("/evaluation/runs/{run_id}", response_model=ApiResponse[RunOut])
async def get_run(run_id: int, context: KnowledgeReadContext, session: DbSession) -> ApiResponse[RunOut]:
    repo = EvaluationRepository(session, context.tenant_id)
    row = await repo.get_run(run_id)
    if row is None:
        from app.core.exceptions import AppError

        raise AppError("评测任务不存在或不可访问", code=40483, status_code=404)
    names = await repo.experiment_names([row.experiment_id])
    return ok(EvaluationService._run_out(row, experiment_name=names.get(row.experiment_id)))


@router.get("/evaluation/runs/{run_id}/results", response_model=ApiResponse[list[ResultOut]])
async def list_results(run_id: int, context: KnowledgeReadContext, session: DbSession) -> ApiResponse[list[ResultOut]]:
    repo = EvaluationRepository(session, context.tenant_id)
    run = await repo.get_run(run_id)
    if run is None:
        from app.core.exceptions import AppError

        raise AppError("评测任务不存在或不可访问", code=40483, status_code=404)
    rows = await repo.list_results(run.id)
    version = await repo.get_version(run.dataset_id, run.dataset_version)
    expected_by_id: dict[int, str | None] = {}
    for case in ((version.snapshot or {}).get("cases") or []) if version is not None else []:
        try:
            expected_by_id[int(case["id"])] = case.get("expected_answer")
        except (KeyError, TypeError, ValueError):
            continue
    return ok([_result_out(item, expected_by_id.get(item.case_id)) for item in rows])


@router.post("/evaluation/runs/{run_id}/cancel", response_model=ApiResponse[RunOut])
async def cancel_run(run_id: int, context: KnowledgeUpdateContext, session: DbSession) -> ApiResponse[RunOut]:
    return ok(_run_out(await EvaluationRunService(session, context).cancel(run_id)), "已请求取消")


@router.post("/evaluation/runs/{run_id}/pause", response_model=ApiResponse[RunOut])
async def pause_run(run_id: int, context: KnowledgeUpdateContext, session: DbSession) -> ApiResponse[RunOut]:
    return ok(_run_out(await EvaluationRunService(session, context).pause(run_id)), "已请求暂停")


@router.post("/evaluation/runs/{run_id}/resume", response_model=ApiResponse[RunOut])
async def resume_run(
    run_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
    background: BackgroundTasks,
    payload: RunResumeIn | None = None,
) -> ApiResponse[RunOut]:
    body = payload or RunResumeIn()
    row = await EvaluationRunService(session, context).resume(
        run_id,
        token_budget=body.token_budget,
        cost_budget_usd=body.cost_budget_usd,
    )
    _schedule_eval_run(background, row.id)
    return ok(_run_out(row), "已继续运行")


@router.post("/evaluation/runs/{run_id}/retry", response_model=ApiResponse[RunOut])
async def retry_run(
    run_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
    background: BackgroundTasks,
) -> ApiResponse[RunOut]:
    row = await EvaluationRunService(session, context).retry(run_id)
    _schedule_eval_run(background, row.id)
    return ok(_run_out(row), "已重新排队")


@router.post("/evaluation/runs/{run_id}/retry-failed", response_model=ApiResponse[RunOut])
async def retry_failed_run(
    run_id: int,
    context: KnowledgeUpdateContext,
    session: DbSession,
    background: BackgroundTasks,
) -> ApiResponse[RunOut]:
    row = await EvaluationRunService(session, context).retry_failed(run_id)
    _schedule_eval_run(background, row.id)
    return ok(_run_out(row), "已重试失败题目")


@router.post("/evaluation/results/{result_id}/human", response_model=ApiResponse[ResultOut])
async def human_override(
    result_id: int,
    payload: HumanOverrideIn,
    context: KnowledgeUpdateContext,
    session: DbSession,
) -> ApiResponse[ResultOut]:
    repo = EvaluationRepository(session, context.tenant_id)
    row = await repo.get_result(result_id)
    if row is None:
        from app.core.exceptions import AppError

        raise AppError("评测结果不存在或不可访问", code=40484, status_code=404)
    row.human_override = payload.model_dump()
    await session.commit()
    await session.refresh(row)
    return ok(_result_out(row))


@router.get("/evaluation/compare/cases", response_model=ApiResponse[CaseDiagnosisOut])
async def compare_cases(
    context: KnowledgeReadContext,
    session: DbSession,
    baseline_id: int = Query(description="对照 Run"),
    candidate_id: int = Query(description="待比较 Run"),
) -> ApiResponse[CaseDiagnosisOut]:
    """按 case_id 对齐两份结果。不重新跑检索，也不调用 Judge。"""
    from app.evaluation.diagnose import align_case_results, usage_snapshot

    repo = EvaluationRepository(session, context.tenant_id)
    baseline = await repo.get_run(baseline_id)
    candidate = await repo.get_run(candidate_id)
    if baseline is None or candidate is None:
        from app.core.exceptions import AppError

        raise AppError("评测任务不存在或不可访问", code=40483, status_code=404)
    comparable = True
    reason = None
    if baseline.dataset_id != candidate.dataset_id or baseline.dataset_version != candidate.dataset_version:
        comparable = False
        reason = "数据集版本不同，不能直接比较"
    left_snap = baseline.config_snapshot or {}
    right_snap = candidate.config_snapshot or {}
    if left_snap.get("embedding_model") != right_snap.get("embedding_model") or left_snap.get(
        "embedding_dimensions"
    ) != right_snap.get("embedding_dimensions"):
        comparable = False
        reason = (reason + "；" if reason else "") + "Embedding 或索引维度不同，不能直接比较"
    version = await repo.get_version(baseline.dataset_id, baseline.dataset_version)
    meta: dict[int, dict] = {}
    for case in ((version.snapshot or {}).get("cases") or []) if version is not None else []:
        try:
            gold = []
            for judgment in case.get("judgments") or []:
                if judgment.get("stale"):
                    continue
                if int(judgment.get("relevance") or 0) < 1:
                    continue
                gold.append(int(judgment["chunk_id"]))
            meta[int(case["id"])] = {
                "question_type": case.get("question_type"),
                "difficulty": case.get("difficulty"),
                "tags": case.get("tags") or [],
                "gold_chunk_ids": gold,
            }
        except (KeyError, TypeError, ValueError):
            continue
    left_rows = [_result_out(item).model_dump() for item in await repo.list_results(baseline.id)]
    right_rows = [_result_out(item).model_dump() for item in await repo.list_results(candidate.id)]
    aligned = align_case_results(left_rows, right_rows, case_meta=meta)
    return ok(
        CaseDiagnosisOut(
            comparable=comparable,
            incomparable_reason=reason,
            baseline_usage=usage_snapshot(baseline.usage),
            candidate_usage=usage_snapshot(candidate.usage),
            summary=aligned["summary"],
            groups=aligned["groups"],
            recall_bootstrap=aligned["recall_bootstrap"],
            cases=aligned["cases"],
            note=aligned["note"],
        )
    )


@router.get("/evaluation/compare", response_model=ApiResponse[CompareOut])
async def compare_runs(
    context: KnowledgeReadContext,
    session: DbSession,
    run_ids: str = Query(description="逗号分隔的 run id"),
) -> ApiResponse[CompareOut]:
    repo = EvaluationRepository(session, context.tenant_id)
    ids = []
    for raw in run_ids.split(","):
        if raw.strip().isdigit():
            ids.append(int(raw.strip()))
    runs = []
    for item in ids:
        row = await repo.get_run(item)
        if row is None:
            from app.core.exceptions import AppError

            raise AppError("包含无权访问或不存在的评测任务", code=40483, status_code=404)
        runs.append(row)
    if len(runs) < 2:
        from app.core.exceptions import AppError

        raise AppError("至少选择两个实验运行", code=40088, status_code=400)
    comparable = True
    reason = None
    baseline = runs[0]
    for row in runs[1:]:
        if row.dataset_id != baseline.dataset_id or row.dataset_version != baseline.dataset_version:
            comparable = False
            reason = "数据集版本不同，指标非严格可比"
        left = (row.config_snapshot or {}).get("embedding_model")
        right = (baseline.config_snapshot or {}).get("embedding_model")
        if left != right or (row.config_snapshot or {}).get("embedding_dimensions") != (
            baseline.config_snapshot or {}
        ).get("embedding_dimensions"):
            comparable = False
            reason = (reason or "") + " Embedding/索引版本不同，不能直接解读为检索提升。"
    keys = ["hit_rate", "recall", "precision", "mrr", "ndcg"]
    deltas = {}
    base_metrics = baseline.metrics or {}
    for row in runs[1:]:
        item = {}
        current = row.metrics or {}
        for key in keys:
            if base_metrics.get(key) is None or current.get(key) is None:
                item[key] = None
                continue
            base_value = float(base_metrics[key])
            value = float(current[key])
            item[key] = {
                "base": base_value,
                "value": value,
                "delta": value - base_value,
                "delta_pct": None if base_value == 0 else (value - base_value) / base_value * 100,
            }
        deltas[str(row.id)] = item
    return ok(
        CompareOut(
            runs=[_run_out(item) for item in runs],
            comparable=comparable,
            incomparable_reason=reason,
            metric_deltas=deltas,
        )
    )
