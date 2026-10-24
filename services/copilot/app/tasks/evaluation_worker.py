from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid

from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine, open_tenant_session
from app.services.evaluations import ReplayEvaluationRunner
from app.tasks.evaluation_queue import pop_evaluation

logger = logging.getLogger(__name__)


async def scan_recoverable_evaluations(limit: int = 100) -> list[tuple[int, int, int]]:
    """Redis 丢消息时从 PostgreSQL 权威状态扫描无租约任务。"""
    statement = text(
        """
        SELECT tenant_id, user_id, id
        FROM copilot_agent_evaluation_runs
        WHERE status IN ('QUEUED','RUNNING')
          AND (lease_until IS NULL OR lease_until <= now())
        ORDER BY created_at
        LIMIT :limit
        """
    )
    async with engine.connect() as connection:
        rows = (await connection.execute(statement, {"limit": limit})).all()
    return [(int(x.tenant_id), int(x.user_id), int(x.id)) for x in rows]


async def execute_evaluation(tenant_id: int, user_id: int, run_id: int, owner: str) -> bool:
    session = open_tenant_session(tenant_id)
    try:
        return await ReplayEvaluationRunner(session, tenant_id, user_id, owner).execute(run_id)
    finally:
        await session.close()


async def cleanup_expired_observability() -> None:
    """按配置清理非业务 ModelCall/Event 观测明细；数据集、Case 与聚合报告不受影响。"""
    days = max(1, settings.evaluation_trace_retention_days)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "DELETE FROM copilot_model_calls "
                "WHERE completed_at IS NOT NULL "
                "AND completed_at < now() - make_interval(days => :days)"
            ),
            {"days": days},
        )
        await connection.execute(
            text(
                "DELETE FROM copilot_agent_evaluation_run_events "
                "WHERE created_at < now() - make_interval(days => :days)"
            ),
            {"days": days},
        )


async def main() -> None:
    owner = f"copilot-eval:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    semaphore = asyncio.Semaphore(max(1, settings.evaluation_max_concurrency))
    last_cleanup = 0.0

    async def run_item(item: tuple[int, int, int]) -> None:
        async with semaphore:
            await execute_evaluation(*item, owner)

    while True:
        item = await pop_evaluation(settings.evaluation_worker_poll_seconds)
        if time.monotonic() - last_cleanup >= 3600:
            await cleanup_expired_observability()
            last_cleanup = time.monotonic()
        items = [item] if item else await scan_recoverable_evaluations()
        if not items:
            continue
        await asyncio.gather(*(run_item(x) for x in items[: settings.evaluation_max_concurrency]))


if __name__ == "__main__":
    asyncio.run(main())
