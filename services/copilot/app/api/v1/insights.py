from typing import cast

from fastapi import APIRouter, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, InsightManageContext, InsightReadContext
from app.erp.client import get_erp_client
from app.insights.detectors import detector_registry
from app.schemas.common import ApiResponse, ok
from app.schemas.insight import (
    BusinessInsightOut,
    InsightAction,
    InsightEventOut,
    InsightNotificationOut,
    InsightRuleCreate,
    InsightRuleOut,
    InsightRulePatch,
    InsightRunOut,
)
from app.services.insights import InsightService

router = APIRouter(tags=["proactive-insights"])


def _service(request: Request, db: DbSession, context: InsightReadContext) -> InsightService:
    return InsightService(
        cast(AsyncSession, db),
        context,
        erp=get_erp_client(),
        access_token=str(getattr(request.state, "access_token", "")),
        request_id=str(getattr(request.state, "request_id", "")),
    )


@router.get("/insight-detectors", response_model=ApiResponse[list[dict]])
async def detectors(context: InsightReadContext):
    return ok(
        [
            {
                "detector_type": x.detector_type,
                "version": x.version,
                "description": x.description,
                "required_permissions": list(x.required_permissions),
                "maximum_result_count": x.maximum_result_count,
            }
            for x in detector_registry.catalog()
        ]
    )


@router.post("/insight-rules", response_model=ApiResponse[InsightRuleOut])
async def create_rule(
    payload: InsightRuleCreate, request: Request, context: InsightManageContext, db: DbSession
):
    return ok(await _service(request, db, context).create_rule(payload))


@router.get("/insight-rules", response_model=ApiResponse[dict])
async def list_rules(
    request: Request,
    context: InsightReadContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(await _service(request, db, context).list_rules(page, page_size))


@router.get("/insight-rules/{rule_id}", response_model=ApiResponse[InsightRuleOut])
async def get_rule(rule_id: int, request: Request, context: InsightReadContext, db: DbSession):
    return ok(await _service(request, db, context).rule(rule_id))


@router.patch("/insight-rules/{rule_id}", response_model=ApiResponse[InsightRuleOut])
async def patch_rule(
    rule_id: int,
    payload: InsightRulePatch,
    request: Request,
    context: InsightManageContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).patch_rule(rule_id, payload))


@router.post("/insight-rules/{rule_id}/run", response_model=ApiResponse[InsightRunOut])
async def run_rule(rule_id: int, request: Request, context: InsightManageContext, db: DbSession):
    return ok(await _service(request, db, context).run_now(rule_id))


@router.get("/insights/dashboard", response_model=ApiResponse[dict])
async def dashboard(request: Request, context: InsightReadContext, db: DbSession):
    return ok(await _service(request, db, context).dashboard())


@router.get("/insights", response_model=ApiResponse[dict])
async def list_insights(
    request: Request,
    context: InsightReadContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    severity: str | None = None,
):
    return ok(await _service(request, db, context).list_insights(page, page_size, status, severity))


@router.get("/insights/{insight_id}", response_model=ApiResponse[BusinessInsightOut])
async def get_insight(
    insight_id: int, request: Request, context: InsightReadContext, db: DbSession
):
    return ok(await _service(request, db, context).insight(insight_id))


async def _transition(
    insight_id: int,
    action: str,
    payload: InsightAction,
    request: Request,
    context: InsightReadContext,
    db: DbSession,
):
    return ok(await _service(request, db, context).transition(insight_id, action, payload))


@router.post("/insights/{insight_id}/acknowledge", response_model=ApiResponse[BusinessInsightOut])
async def acknowledge(
    insight_id: int, request: Request, context: InsightReadContext, db: DbSession
):
    return await _transition(insight_id, "acknowledge", InsightAction(), request, context, db)


@router.post("/insights/{insight_id}/snooze", response_model=ApiResponse[BusinessInsightOut])
async def snooze(
    insight_id: int,
    payload: InsightAction,
    request: Request,
    context: InsightReadContext,
    db: DbSession,
):
    return await _transition(insight_id, "snooze", payload, request, context, db)


@router.post("/insights/{insight_id}/close", response_model=ApiResponse[BusinessInsightOut])
async def close(insight_id: int, request: Request, context: InsightReadContext, db: DbSession):
    return await _transition(insight_id, "close", InsightAction(), request, context, db)


@router.get("/insights/{insight_id}/events", response_model=ApiResponse[list[InsightEventOut]])
async def events(insight_id: int, request: Request, context: InsightReadContext, db: DbSession):
    return ok(await _service(request, db, context).events(insight_id))


@router.get("/insight-runs", response_model=ApiResponse[dict])
async def runs(
    request: Request,
    context: InsightReadContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(await _service(request, db, context).list_runs(page, page_size))


@router.get("/insight-runs/{run_id}", response_model=ApiResponse[InsightRunOut])
async def run_detail(run_id: int, request: Request, context: InsightReadContext, db: DbSession):
    return ok(await _service(request, db, context).run_detail(run_id))


@router.get("/insight-notifications", response_model=ApiResponse[dict])
async def notifications(
    request: Request,
    context: InsightReadContext,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return ok(await _service(request, db, context).notifications(page, page_size))


@router.post(
    "/insight-notifications/{notification_id}/read",
    response_model=ApiResponse[InsightNotificationOut],
)
async def read_notification(
    notification_id: int, request: Request, context: InsightReadContext, db: DbSession
):
    return ok(await _service(request, db, context).read_notification(notification_id))
