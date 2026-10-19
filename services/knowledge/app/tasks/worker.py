"""Knowledge Worker：消费解析 / 切片任务。

本地：uv run python -m app.tasks.worker
进程重启时：文档 RUNNING 标失败；评测 RUNNING 在租约过期后改为 QUEUED 并续跑，保留部分结果。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.event_loop import selector_loop_factory
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentStatus, TaskType
from app.repositories.documents import TaskRepository
from app.repositories.evaluation import EvaluationRepository
from app.services.evaluation_run import EvaluationRunService
from app.services.processing import ProcessingService
from app.tasks.queue import enqueue_eval_run, enqueue_task, pop_queue_item

logger = logging.getLogger(__name__)


async def recover_stale_tasks() -> None:
    """重启后回收过期评测租约，并把 QUEUED 重新入队。文档 RUNNING 仍标失败。"""
    async with SessionLocal() as session:
        repo = TaskRepository(session)
        failed = await repo.fail_stale_running(message="Worker 重启，任务中断，请重试")
        parse_or_chunk_docs = {
            row.document_id for row in failed if row.task_type in {TaskType.PARSE.value, TaskType.CHUNK.value}
        }
        if parse_or_chunk_docs:
            docs = list(
                (
                    await session.scalars(
                        select(KnowledgeDocument).where(KnowledgeDocument.id.in_(parse_or_chunk_docs))
                    )
                ).all()
            )
            for document in docs:
                document.status = KnowledgeDocumentStatus.FAILED.value
                document.error_message = "Worker 重启，任务中断，请重试"
        queued = await repo.list_queued()
        eval_repo = EvaluationRepository(session, 0)
        eval_failed = await eval_repo.pause_stale_running("Worker 重启，已保留部分结果，将从中断处继续")
        eval_queued = await eval_repo.list_queued_runs()
        await session.commit()
        for task in queued:
            await enqueue_task(task.id)
        for run in eval_queued:
            await enqueue_eval_run(run.id)
        if failed or queued or eval_failed or eval_queued:
            logger.info(
                "knowledge worker recovered running=%s queued=%s eval_failed=%s eval_queued=%s",
                len(failed),
                len(queued),
                len(eval_failed),
                len(eval_queued),
            )


async def recover_expired_eval_leases() -> None:
    """空闲时回收租约过期的 RUNNING 评测，避免 Worker 崩溃后任务永久卡住。"""
    async with SessionLocal() as session:
        eval_repo = EvaluationRepository(session, 0)
        recovered = await eval_repo.pause_stale_running("评测租约过期，已保留部分结果，将从中断处继续")
        await session.commit()
        for run in recovered:
            await enqueue_eval_run(run.id)
        if recovered:
            logger.info("knowledge worker reclaimed expired eval leases=%s", len(recovered))


async def handle_one(task_id: int) -> None:
    async with SessionLocal() as session:
        await ProcessingService(session).execute(task_id)


async def handle_eval(run_id: int) -> None:
    from app.evaluation.stages import PauseRun

    try:
        async with SessionLocal() as session:
            await EvaluationRunService(session).execute(run_id)
    except PauseRun:
        logger.info("eval run paused run_id=%s", run_id)


async def run_forever() -> None:
    setup_logging()
    await recover_stale_tasks()
    logger.info("knowledge worker started concurrency=%s", settings.worker_concurrency)
    while True:
        raw = await pop_queue_item(timeout=3)
        if raw is None:
            await recover_expired_eval_leases()
            continue
        try:
            if raw.startswith("eval:"):
                await handle_eval(int(raw.split(":", 1)[1]))
            else:
                await handle_one(int(raw))
        except Exception:
            logger.exception("knowledge worker crashed on item=%s", raw)


def main() -> None:
    asyncio.run(run_forever(), loop_factory=selector_loop_factory)


if __name__ == "__main__":
    main()
