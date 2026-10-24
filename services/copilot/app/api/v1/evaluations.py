from fastapi import APIRouter, Query

from app.api.deps import CopilotContext, DbSession
from app.schemas.common import ApiResponse, ok
from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseImport,
    EvaluationCaseOut,
    EvaluationCasePatch,
    EvaluationCaseRunOut,
    EvaluationComparisonCreate,
    EvaluationComparisonOut,
    EvaluationDatasetCreate,
    EvaluationDatasetDetailOut,
    EvaluationDatasetOut,
    EvaluationDatasetPatch,
    EvaluationDatasetVersionOut,
    EvaluationHumanReview,
    EvaluationRunCreate,
    EvaluationRunDetailOut,
    EvaluationRunOut,
)
from app.services.evaluations import AgentEvaluationService
from app.tasks.evaluation_queue import enqueue_evaluation

router = APIRouter(prefix="/evaluations", tags=["agent-evaluations"])


def _service(db: DbSession, context: CopilotContext) -> AgentEvaluationService:
    return AgentEvaluationService(db, context)


@router.post("/datasets", response_model=ApiResponse[EvaluationDatasetOut])
async def create_dataset(payload: EvaluationDatasetCreate, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).create_dataset(payload))


@router.get("/datasets", response_model=ApiResponse[dict])
async def list_datasets(
    context: CopilotContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(await _service(db, context).list_datasets(page, page_size))


@router.get("/datasets/{dataset_id}", response_model=ApiResponse[EvaluationDatasetDetailOut])
async def dataset_detail(dataset_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).dataset_detail(dataset_id))


@router.patch("/datasets/{dataset_id}", response_model=ApiResponse[EvaluationDatasetOut])
async def patch_dataset(
    dataset_id: int, payload: EvaluationDatasetPatch, context: CopilotContext, db: DbSession
):
    return ok(await _service(db, context).patch_dataset(dataset_id, payload))


@router.post("/datasets/{dataset_id}/cases", response_model=ApiResponse[EvaluationCaseOut])
async def create_case(
    dataset_id: int, payload: EvaluationCaseCreate, context: CopilotContext, db: DbSession
):
    return ok(await _service(db, context).add_case(dataset_id, payload))


@router.get("/datasets/{dataset_id}/cases", response_model=ApiResponse[list[EvaluationCaseOut]])
async def list_cases(dataset_id: int, context: CopilotContext, db: DbSession):
    return ok((await _service(db, context).dataset_detail(dataset_id)).cases)


@router.post("/datasets/{dataset_id}/cases/import", response_model=ApiResponse[dict])
async def import_cases(
    dataset_id: int, payload: EvaluationCaseImport, context: CopilotContext, db: DbSession
):
    return ok(await _service(db, context).import_cases(dataset_id, payload))


@router.post("/datasets/{dataset_id}/cases/import-v8", response_model=ApiResponse[dict])
async def import_v8_cases(dataset_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).import_v8_baseline(dataset_id))


@router.post("/datasets/{dataset_id}/cases/import-v9", response_model=ApiResponse[dict])
async def import_v9_cases(dataset_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).import_v9_catalog(dataset_id))


@router.patch("/cases/{case_id}", response_model=ApiResponse[EvaluationCaseOut])
async def patch_case(
    case_id: int, payload: EvaluationCasePatch, context: CopilotContext, db: DbSession
):
    return ok(await _service(db, context).patch_case(case_id, payload))


@router.delete("/cases/{case_id}", response_model=ApiResponse[dict])
async def delete_case(case_id: int, context: CopilotContext, db: DbSession):
    await _service(db, context).delete_case(case_id)
    return ok({"deleted": True})


@router.post(
    "/datasets/{dataset_id}/freeze", response_model=ApiResponse[EvaluationDatasetVersionOut]
)
async def freeze_dataset(dataset_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).freeze(dataset_id))


@router.get(
    "/datasets/{dataset_id}/versions", response_model=ApiResponse[list[EvaluationDatasetVersionOut]]
)
async def list_versions(dataset_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).versions(dataset_id))


@router.post("/runs", response_model=ApiResponse[EvaluationRunOut])
async def create_run(payload: EvaluationRunCreate, context: CopilotContext, db: DbSession):
    row = await _service(db, context).create_run(payload)
    await enqueue_evaluation(context.tenant_id, context.user_id, row.id)
    return ok(row)


@router.get("/runs", response_model=ApiResponse[dict])
async def list_runs(
    context: CopilotContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(await _service(db, context).list_runs(page, page_size))


@router.get("/runs/{run_id}", response_model=ApiResponse[EvaluationRunDetailOut])
async def run_detail(run_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).run_detail(run_id))


@router.get("/runs/{run_id}/cases", response_model=ApiResponse[list])
async def run_cases(run_id: int, context: CopilotContext, db: DbSession):
    return ok((await _service(db, context).run_detail(run_id)).cases)


@router.patch(
    "/runs/{run_id}/cases/{case_run_id}/review",
    response_model=ApiResponse[EvaluationCaseRunOut],
)
async def review_case(
    run_id: int,
    case_run_id: int,
    payload: EvaluationHumanReview,
    context: CopilotContext,
    db: DbSession,
):
    return ok(await _service(db, context).review_case(run_id, case_run_id, payload))


@router.get("/runs/{run_id}/metrics", response_model=ApiResponse[dict])
async def run_metrics(run_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).metrics(run_id))


@router.post("/runs/{run_id}/pause", response_model=ApiResponse[EvaluationRunOut])
async def pause_run(run_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).pause(run_id))


@router.post("/runs/{run_id}/resume", response_model=ApiResponse[EvaluationRunOut])
async def resume_run(run_id: int, context: CopilotContext, db: DbSession):
    row = await _service(db, context).resume(run_id)
    await enqueue_evaluation(context.tenant_id, context.user_id, row.id)
    return ok(row)


@router.post("/runs/{run_id}/cancel", response_model=ApiResponse[EvaluationRunOut])
async def cancel_run(run_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).cancel(run_id))


@router.post("/comparisons", response_model=ApiResponse[EvaluationComparisonOut])
async def create_comparison(
    payload: EvaluationComparisonCreate, context: CopilotContext, db: DbSession
):
    return ok(await _service(db, context).compare(payload))


@router.get("/comparisons/{comparison_id}", response_model=ApiResponse[EvaluationComparisonOut])
async def get_comparison(comparison_id: int, context: CopilotContext, db: DbSession):
    return ok(await _service(db, context).comparison(comparison_id))
