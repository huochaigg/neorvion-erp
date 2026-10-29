from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from app.core.config import settings
from app.core.service_tokens import ServiceTokenClient
from app.core.tenant import TenantContext
from app.db.session import engine, open_tenant_session
from app.erp.client import get_erp_client
from app.insights.detectors import detector_registry
from app.models.insight import InsightDetectionRun, InsightRule
from app.services.insights import InsightService
from app.tasks.insight_queue import pop_insight

logger = logging.getLogger(__name__)


async def scan_recoverable_insights(limit: int = 100) -> list[tuple[int, int]]:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT tenant_id, id FROM copilot_insight_detection_runs "
                    "WHERE status IN ('QUEUED','RUNNING') "
                    "AND (lease_until IS NULL OR lease_until <= now()) "
                    "AND attempt_count < :attempts ORDER BY created_at LIMIT :limit"
                ),
                {"attempts": settings.insight_max_attempts, "limit": limit},
            )
        ).all()
    return [(int(row.tenant_id), int(row.id)) for row in rows]


async def execute_insight(
    tenant_id: int, run_id: int, owner: str, tokens: ServiceTokenClient
) -> None:
    session = open_tenant_session(tenant_id)
    heartbeat: asyncio.Task | None = None
    try:
        run = await session.scalar(
            select(InsightDetectionRun)
            .where(
                InsightDetectionRun.tenant_id == tenant_id,
                InsightDetectionRun.id == run_id,
            )
            .with_for_update()
        )
        now = datetime.now(UTC)
        if (
            run is None
            or run.status not in {"QUEUED", "RUNNING"}
            or (run.lease_until is not None and run.lease_until > now and run.lease_owner != owner)
        ):
            return
        rule = await session.scalar(
            select(InsightRule).where(
                InsightRule.tenant_id == tenant_id, InsightRule.id == run.rule_id
            )
        )
        if rule is None or not rule.enabled:
            run.status = "CANCELLED"
            run.safe_error = "检测规则已停用"
            run.finished_at = now
            await session.commit()
            return
        required = list(detector_registry.get(rule.detector_type).required_permissions)
        resources: dict[str, list[str]] = {}
        if rule.config.get("warehouse_id") is not None:
            resources["warehouse"] = [str(rule.config["warehouse_id"])]
        if rule.config.get("sku_code"):
            resources["sku"] = [str(rule.config["sku_code"])]
        run.status = "RUNNING"
        run.attempt_count += 1
        run.started_at = run.started_at or now
        run.lease_owner = owner
        run.lease_until = now + timedelta(seconds=settings.insight_lease_seconds)
        await session.commit()
        heartbeat = asyncio.create_task(_heartbeat(tenant_id, run_id, owner))
        token = await tokens.token(
            audience=settings.erp_jwt_audience,
            tenant_id=tenant_id,
            scopes=required,
            resources=resources,
        )
        context = TenantContext(
            user_id=0,
            tenant_id=tenant_id,
            member_id=0,
            is_owner=False,
            role="SERVICE",
            permission_codes=frozenset(required),
            subject_type="SERVICE",
            service_id=settings.insight_service_id,
            service_scopes=frozenset(required),
            service_resources={key: tuple(value) for key, value in resources.items()},
        )
        service = InsightService(
            session,
            context,
            erp=get_erp_client(),
            access_token=token,
            request_id=f"insight-worker-{run_id}",
        )
        await service.execute_queued(run_id)
    except Exception as exc:
        await session.rollback()
        row = await session.scalar(
            select(InsightDetectionRun)
            .where(
                InsightDetectionRun.tenant_id == tenant_id,
                InsightDetectionRun.id == run_id,
            )
            .with_for_update()
        )
        if row is not None:
            retry = row.attempt_count < settings.insight_max_attempts
            row.status = "QUEUED" if retry else "FAILED"
            row.safe_error = str(exc)[:255]
            row.error_code = int(getattr(exc, "code", 50091))
            row.lease_owner = None
            row.lease_until = (
                datetime.now(UTC) + timedelta(seconds=min(300, 2**row.attempt_count))
                if retry
                else None
            )
            row.finished_at = None if retry else datetime.now(UTC)
            await session.commit()
        logger.exception("insight worker failed tenant_id=%s run_id=%s", tenant_id, run_id)
    finally:
        if heartbeat is not None:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        await session.close()


async def _heartbeat(tenant_id: int, run_id: int, owner: str) -> None:
    """使用独立会话续租，避免与检测任务共享 AsyncSession。"""
    interval = max(5, settings.insight_lease_seconds // 3)
    while True:
        await asyncio.sleep(interval)
        session = open_tenant_session(tenant_id)
        try:
            row = await session.scalar(
                select(InsightDetectionRun).where(
                    InsightDetectionRun.tenant_id == tenant_id,
                    InsightDetectionRun.id == run_id,
                    InsightDetectionRun.status == "RUNNING",
                    InsightDetectionRun.lease_owner == owner,
                )
            )
            if row is None:
                return
            row.lease_until = datetime.now(UTC) + timedelta(seconds=settings.insight_lease_seconds)
            await session.commit()
        finally:
            await session.close()


async def main() -> None:
    if not settings.insight_scheduler_enabled:
        raise RuntimeError("INSIGHT_SCHEDULER_ENABLED=false，周期 Worker 拒绝启动")
    tokens = ServiceTokenClient(
        settings.iam_service_token_url,
        settings.insight_service_id,
        settings.insight_service_secret.get_secret_value(),
    )
    owner = f"copilot-insight:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    semaphore = asyncio.Semaphore(max(1, settings.insight_max_concurrency))

    async def run_item(item: tuple[int, int]) -> None:
        async with semaphore:
            await execute_insight(*item, owner, tokens)

    while True:
        item = await pop_insight(settings.insight_worker_poll_seconds)
        items = [item] if item else await scan_recoverable_insights()
        if items:
            await asyncio.gather(
                *(run_item(value) for value in items[: settings.insight_max_concurrency])
            )


if __name__ == "__main__":
    asyncio.run(main())
