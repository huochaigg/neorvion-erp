from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.session import engine, open_tenant_session
from app.models.insight import InsightDetectionRun, InsightRule
from app.tasks.insight_queue import enqueue_insight

logger = logging.getLogger(__name__)


async def scan_due_rules(limit: int = 100) -> list[tuple[int, int]]:
    """跨租户只扫描到期标识；真正创建运行仍在绑定租户的会话内完成。"""
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT tenant_id, id FROM copilot_insight_rules "
                    "WHERE enabled = true AND next_run_at <= now() "
                    "ORDER BY next_run_at LIMIT :limit"
                ),
                {"limit": limit},
            )
        ).all()
    return [(int(row.tenant_id), int(row.id)) for row in rows]


async def schedule_rule(tenant_id: int, rule_id: int) -> int | None:
    """锁定规则并以计划窗口生成唯一 Run，防止多个 Scheduler 重复投递。"""
    session = open_tenant_session(tenant_id)
    try:
        rule = await session.scalar(
            select(InsightRule)
            .where(InsightRule.tenant_id == tenant_id, InsightRule.id == rule_id)
            .with_for_update(skip_locked=True)
        )
        now = datetime.now(UTC)
        if rule is None or not rule.enabled or rule.next_run_at is None or rule.next_run_at > now:
            return None
        scheduled_at = rule.next_run_at
        schedule_key = f"interval:{scheduled_at.isoformat()}"
        run = InsightDetectionRun(
            tenant_id=tenant_id,
            rule_id=rule.id,
            requested_by=None,
            schedule_key=schedule_key,
            detector_version=rule.detector_version,
            rule_snapshot={
                "name": rule.name,
                "detector_type": rule.detector_type,
                "detector_version": rule.detector_version,
                "config": rule.config,
                "timezone": rule.timezone,
                "interval_minutes": rule.interval_minutes,
            },
            status="QUEUED",
        )
        session.add(run)
        rule.next_run_at = scheduled_at + timedelta(minutes=rule.interval_minutes)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        await session.refresh(run)
        return run.id
    finally:
        await session.close()


async def run_once() -> int:
    scheduled = 0
    for tenant_id, rule_id in await scan_due_rules():
        run_id = await schedule_rule(tenant_id, rule_id)
        if run_id is not None:
            await enqueue_insight(tenant_id, run_id)
            scheduled += 1
    return scheduled


async def main() -> None:
    if not settings.insight_scheduler_enabled:
        raise RuntimeError("INSIGHT_SCHEDULER_ENABLED=false，安全服务身份完成配置前拒绝启动")
    if not settings.insight_service_id or not settings.insight_service_secret.get_secret_value():
        raise RuntimeError("周期洞察缺少 INSIGHT_SERVICE_ID/INSIGHT_SERVICE_SECRET")
    logger.info("copilot insight scheduler started")
    while True:
        try:
            await run_once()
        except Exception:
            logger.exception("insight scheduler scan failed")
        await asyncio.sleep(max(5, settings.insight_worker_poll_seconds))


if __name__ == "__main__":
    asyncio.run(main())
