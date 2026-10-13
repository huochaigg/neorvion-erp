"""Knowledge Worker：消费解析 / 切片任务。

本地：uv run python -m app.tasks.worker
进程重启时把遗留 RUNNING 标为失败，并把 QUEUED 重新投递。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.event_loop import selector_loop_factory
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentStatus
from app.repositories.documents import TaskRepository
from app.services.processing import ProcessingService
from app.tasks.queue import enqueue_task, pop_task

logger = logging.getLogger(__name__)


async def recover_stale_tasks() -> None:
    """重启后：中断的 RUNNING 无法确认副作用，标记失败；QUEUED 重新入队。"""
    async with SessionLocal() as session:
        repo = TaskRepository(session)
        failed = await repo.fail_stale_running(message="Worker 重启，任务中断，请重试")
        if failed:
            docs = list(
                (
                    await session.scalars(
                        select(KnowledgeDocument).where(
                            KnowledgeDocument.status == KnowledgeDocumentStatus.PROCESSING.value
                        )
                    )
                ).all()
            )
            for document in docs:
                document.status = KnowledgeDocumentStatus.FAILED.value
                document.error_message = "Worker 重启，任务中断，请重试"
        queued = await repo.list_queued()
        await session.commit()
        for task in queued:
            await enqueue_task(task.id)
        if failed or queued:
            logger.info("knowledge worker recovered running=%s queued=%s", failed, len(queued))


async def handle_one(task_id: int) -> None:
    async with SessionLocal() as session:
        await ProcessingService(session).execute(task_id)


async def run_forever() -> None:
    setup_logging()
    await recover_stale_tasks()
    logger.info("knowledge worker started concurrency=%s", settings.worker_concurrency)
    while True:
        task_id = await pop_task(timeout=3)
        if task_id is None:
            continue
        try:
            await handle_one(task_id)
        except Exception:
            logger.exception("knowledge worker crashed on task_id=%s", task_id)


def main() -> None:
    asyncio.run(run_forever(), loop_factory=selector_loop_factory)


if __name__ == "__main__":
    main()
