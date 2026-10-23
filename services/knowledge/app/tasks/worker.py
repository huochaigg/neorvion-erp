"""Knowledge Worker：消费解析 / 切片任务。

本地：uv run python -m app.tasks.worker
进程重启时：文档 RUNNING 标失败；评测 RUNNING 在租约过期后改为 QUEUED 并续跑，保留部分结果。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import cast

from neorvion_db import PrivilegedOperation, open_privileged_async_session, privileged_option
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.event_loop import selector_loop_factory
from app.core.logging import setup_logging
from app.db.isolation import REGISTRY
from app.db.session import engine, open_tenant_session
from app.db.system_access import PRIVILEGED_CALLERS, PRIVILEGED_FLUSH_MODELS
from app.models.knowledge import KnowledgeDocument, KnowledgeDocumentStatus, TaskType
from app.repositories.system_queue import (
    fail_stale_tasks,
    list_queued_label_jobs,
    list_queued_runs,
    list_queued_tasks,
    pause_stale_runs,
    requeue_stale_label_jobs,
)
from app.services.evaluation_run import EvaluationRunService
from app.services.processing import ProcessingService
from app.tasks.queue import enqueue_eval_run, enqueue_label_job, enqueue_task, pop_queue_item

logger = logging.getLogger(__name__)


def _open_claim():
    """必须在本模块直接打开。放到其他模块会让调用方白名单失效。"""
    return open_privileged_async_session(
        PrivilegedOperation.WORKER_CLAIM,
        registry=REGISTRY,
        allowed_callers=PRIVILEGED_CALLERS[PrivilegedOperation.WORKER_CLAIM],
        bind=engine,
        flush_models=PRIVILEGED_FLUSH_MODELS[PrivilegedOperation.WORKER_CLAIM],
    )


def _positive_tenant(value: object) -> int | None:
    if type(value) is int and value > 0:
        return value
    return None


async def recover_stale_tasks() -> None:
    """重启后回收过期评测租约，并把 QUEUED 重新入队。文档 RUNNING 仍标失败。"""
    async with _open_claim() as privileged:
        session = cast(AsyncSession, cast(object, privileged))
        failed = await fail_stale_tasks(session, message="Worker 重启，任务中断，请重试")
        parse_or_chunk_docs = {
            row.document_id for row in failed if row.task_type in {TaskType.PARSE.value, TaskType.CHUNK.value}
        }
        if parse_or_chunk_docs:
            docs = list(
                (
                    await session.scalars(
                        select(KnowledgeDocument)
                    .where(KnowledgeDocument.id.in_(parse_or_chunk_docs))
                    .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
                    )
                ).all()
            )
            for document in docs:
                document.status = KnowledgeDocumentStatus.FAILED.value
                document.error_message = "Worker 重启，任务中断，请重试"
        queued = await list_queued_tasks(session)
        eval_failed = await pause_stale_runs(session, "Worker 重启，已保留部分结果，将从中断处继续")
        eval_queued = await list_queued_runs(session)
        label_failed = await requeue_stale_label_jobs(session, "Worker 重启，已保留部分确认结果，将从中断处继续")
        label_queued = await list_queued_label_jobs(session)
        await session.commit()
        for task in queued:
            await enqueue_task(task.id)
        for run in eval_queued:
            await enqueue_eval_run(run.id)
        for job in label_queued:
            await enqueue_label_job(job.id)
        if failed or queued or eval_failed or eval_queued or label_failed or label_queued:
            logger.info(
                "knowledge worker recovered running=%s queued=%s eval_failed=%s eval_queued=%s label_failed=%s label_queued=%s",
                len(failed),
                len(queued),
                len(eval_failed),
                len(eval_queued),
                len(label_failed),
                len(label_queued),
            )


async def recover_expired_eval_leases() -> None:
    """空闲时回收租约过期的 RUNNING 评测，以及长时间无进度的标注任务。"""
    async with _open_claim() as privileged:
        session = cast(AsyncSession, cast(object, privileged))
        recovered = await pause_stale_runs(session, "评测租约过期，已保留部分结果，将从中断处继续")
        labels = await requeue_stale_label_jobs(
            session,
            "标注任务中断，已保留部分结果，将从中断处继续",
            stale_after=timedelta(minutes=10),
        )
        await session.commit()
        for run in recovered:
            await enqueue_eval_run(run.id)
        for job in labels:
            await enqueue_label_job(job.id)
        if recovered or labels:
            logger.info(
                "knowledge worker reclaimed expired eval leases=%s stale_label_jobs=%s",
                len(recovered),
                len(labels),
            )


async def _task_tenant(task_id: int) -> int | None:
    """只从任务行读取 tenant_id。队列载荷里的数字不能代替数据库。"""
    from app.models.knowledge import DocumentProcessingTask

    async with _open_claim() as privileged:
        session = cast(AsyncSession, cast(object, privileged))
        task = await session.scalar(
            select(DocumentProcessingTask)
            .where(DocumentProcessingTask.id == task_id)
            .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
        )
        if task is None:
            return None
        return _positive_tenant(task.tenant_id)


async def _run_tenant(run_id: int) -> int | None:
    """评测执行前先读运行行上的租户，再打开该租户的业务会话。"""
    from app.models.evaluation import EvaluationRun

    async with _open_claim() as privileged:
        session = cast(AsyncSession, cast(object, privileged))
        run = await session.scalar(
            select(EvaluationRun)
            .where(EvaluationRun.id == run_id)
            .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
        )
        if run is None:
            return None
        return _positive_tenant(run.tenant_id)


async def handle_one(task_id: int) -> None:
    tenant_id = await _task_tenant(task_id)
    if tenant_id is None:
        logger.error("knowledge task missing tenant task_id=%s", task_id)
        return
    async with open_tenant_session(tenant_id) as session:
        await ProcessingService(session).execute(task_id)


async def _label_tenant(job_id: int) -> int | None:
    from app.models.evaluation import EvaluationLabelJob

    async with _open_claim() as privileged:
        session = cast(AsyncSession, cast(object, privileged))
        job = await session.scalar(
            select(EvaluationLabelJob)
            .where(EvaluationLabelJob.id == job_id)
            .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
        )
        if job is None:
            return None
        return _positive_tenant(job.tenant_id)


async def handle_label(job_id: int) -> None:
    from app.services.label_suggestion import execute_label_job

    tenant_id = await _label_tenant(job_id)
    if tenant_id is None:
        logger.error("knowledge label missing tenant job_id=%s", job_id)
        return
    await execute_label_job(job_id)


async def handle_eval(run_id: int) -> None:
    from app.evaluation.stages import PauseRun

    tenant_id = await _run_tenant(run_id)
    if tenant_id is None:
        logger.error("knowledge eval missing tenant run_id=%s", run_id)
        return
    try:
        async with open_tenant_session(tenant_id) as session:
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
            elif raw.startswith("label:"):
                await handle_label(int(raw.split(":", 1)[1]))
            else:
                await handle_one(int(raw))
        except Exception:
            logger.exception("knowledge worker crashed on item=%s", raw)


def main() -> None:
    asyncio.run(run_forever(), loop_factory=selector_loop_factory)


if __name__ == "__main__":
    # python -m app.tasks.worker 会把本文件标成 __main__，特权领取只认 app.tasks.worker。
    from app.tasks.worker import main as _main

    _main()
