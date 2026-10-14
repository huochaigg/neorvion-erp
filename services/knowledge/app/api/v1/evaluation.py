from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import PlainTextResponse

from app.api.deps import (
    DbSession,
    KnowledgeCreateContext,
    KnowledgeDeleteContext,
    KnowledgeReadContext,
    KnowledgeUpdateContext,
)
from app.models.evaluation import EvaluationRun
from app.repositories.evaluation import EvaluationRepository
from app.schemas.common import ApiResponse, ok
from app.schemas.evaluation import (
    CaseCreateIn,
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
    ExperimentCreateIn,
    ExperimentListOut,
    ExperimentOut,
    ExperimentUpdateIn,
    HumanOverrideIn,
    ImportResultOut,
    JudgmentIn,
    ResultOut,
    RunListOut,
    RunOut,
)
from app.schemas.ops import ProbeIn, ProbeOut
from app.services.evaluation import EvaluationService
from app.services.evaluation_run import EvaluationRunService

router = APIRouter(tags=["knowledge-evaluation"])


def _run_out(row: EvaluationRun) -> RunOut:
    return RunOut(
        id=row.id,
        experiment_id=row.experiment_id,
        dataset_id=row.dataset_id,
        dataset_version=row.dataset_version,
        status=row.status,
        progress=row.progress,
        attempt=row.attempt,
        error_message=row.error_message,
        config_snapshot=dict(row.config_snapshot or {}),
        dataset_snapshot_meta=dict(row.dataset_snapshot_meta or {}),
        metrics=row.metrics,
        usage=row.usage,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
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


@router.post("/evaluation/datasets/{dataset_id}/freeze", response_model=ApiResponse[dict])
async def freeze_dataset(dataset_id: int, context: KnowledgeUpdateContext, session: DbSession) -> ApiResponse[dict]:
    row = await EvaluationService(session, context).freeze_version(dataset_id)
    return ok({"version": row.version, "ready_count": row.ready_count, "stale_judgment_count": row.stale_judgment_count})


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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[ExperimentListOut]:
    return ok(await EvaluationService(session, context).list_experiments(dataset_id, page, page_size))


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
    experiment_id: int, context: KnowledgeCreateContext, session: DbSession
) -> ApiResponse[RunOut]:
    row = await EvaluationRunService(session, context).start(experiment_id)
    return ok(_run_out(row), "已排队评测")


@router.get("/evaluation/runs", response_model=ApiResponse[RunListOut])
async def list_runs(
    context: KnowledgeReadContext,
    session: DbSession,
    experiment_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[RunListOut]:
    repo = EvaluationRepository(session, context.tenant_id)
    rows, total = await repo.list_runs(experiment_id=experiment_id, page=page, page_size=page_size)
    return ok(RunListOut(items=[_run_out(item) for item in rows], total=total, page=page, page_size=page_size))


@router.get("/evaluation/runs/{run_id}", response_model=ApiResponse[RunOut])
async def get_run(run_id: int, context: KnowledgeReadContext, session: DbSession) -> ApiResponse[RunOut]:
    repo = EvaluationRepository(session, context.tenant_id)
    row = await repo.get_run(run_id)
    if row is None:
        from app.core.exceptions import AppError

        raise AppError("评测任务不存在或不可访问", code=40483, status_code=404)
    return ok(_run_out(row))


@router.get("/evaluation/runs/{run_id}/results", response_model=ApiResponse[list[ResultOut]])
async def list_results(run_id: int, context: KnowledgeReadContext, session: DbSession) -> ApiResponse[list[ResultOut]]:
    repo = EvaluationRepository(session, context.tenant_id)
    run = await repo.get_run(run_id)
    if run is None:
        from app.core.exceptions import AppError

        raise AppError("评测任务不存在或不可访问", code=40483, status_code=404)
    rows = await repo.list_results(run.id)
    return ok(
        [
            ResultOut(
                id=item.id,
                run_id=item.run_id,
                case_id=item.case_id,
                question=item.question,
                is_unanswerable=item.is_unanswerable,
                retrieved=list(item.retrieved or []),
                retrieval_metrics=item.retrieval_metrics,
                answer=item.answer,
                generation_metrics=item.generation_metrics,
                judge_error=item.judge_error,
                human_override=item.human_override,
                latency_ms=item.latency_ms,
                error_message=item.error_message,
            )
            for item in rows
        ]
    )


@router.post("/evaluation/runs/{run_id}/cancel", response_model=ApiResponse[RunOut])
async def cancel_run(run_id: int, context: KnowledgeUpdateContext, session: DbSession) -> ApiResponse[RunOut]:
    return ok(_run_out(await EvaluationRunService(session, context).cancel(run_id)), "已请求取消")


@router.post("/evaluation/runs/{run_id}/retry", response_model=ApiResponse[RunOut])
async def retry_run(run_id: int, context: KnowledgeUpdateContext, session: DbSession) -> ApiResponse[RunOut]:
    return ok(_run_out(await EvaluationRunService(session, context).retry(run_id)), "已重新排队")


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
    return ok(
        ResultOut(
            id=row.id,
            run_id=row.run_id,
            case_id=row.case_id,
            question=row.question,
            is_unanswerable=row.is_unanswerable,
            retrieved=list(row.retrieved or []),
            retrieval_metrics=row.retrieval_metrics,
            answer=row.answer,
            generation_metrics=row.generation_metrics,
            judge_error=row.judge_error,
            human_override=row.human_override,
            latency_ms=row.latency_ms,
            error_message=row.error_message,
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
