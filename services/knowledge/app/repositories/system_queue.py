"""Knowledge Worker 的全局领取与回收。业务请求不要调用这些函数。"""

from datetime import UTC, datetime, timedelta

from neorvion_db import PrivilegedOperation, privileged_option
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import EvaluationLabelJob, EvaluationRun, LabelJobStatus, RunStatus
from app.models.knowledge import DocumentProcessingTask, TaskStatus


async def list_queued_tasks(session: AsyncSession) -> list[DocumentProcessingTask]:
    """扫描全部排队文档任务。业务处理阶段再按行上的租户打开会话。"""
    stmt = (
        select(DocumentProcessingTask)
        .where(DocumentProcessingTask.status == TaskStatus.QUEUED.value)
        .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
    )
    return list((await session.scalars(stmt)).all())


async def fail_stale_tasks(session: AsyncSession, *, message: str) -> list[DocumentProcessingTask]:
    """启动时把仍在 RUNNING 的文档任务标为失败。不按单一租户过滤。"""
    stmt = (
        select(DocumentProcessingTask)
        .where(DocumentProcessingTask.status == TaskStatus.RUNNING.value)
        .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
    )
    rows = list((await session.scalars(stmt)).all())
    now = datetime.now(UTC)
    for row in rows:
        row.status = TaskStatus.FAILED.value
        row.error_message = message
        row.finished_at = now
    return rows


async def list_queued_runs(session: AsyncSession) -> list[EvaluationRun]:
    """扫描全部排队评测。执行前再读取运行行上的租户。"""
    stmt = (
        select(EvaluationRun)
        .where(EvaluationRun.status == RunStatus.QUEUED.value)
        .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
    )
    return list((await session.scalars(stmt)).all())


async def pause_stale_runs(session: AsyncSession, message: str) -> list[EvaluationRun]:
    """回收租约已过期的 RUNNING 评测，保留已落库题目。仍在租约内的任务不抢。"""
    now = datetime.now(UTC)
    stmt = (
        select(EvaluationRun)
        .where(EvaluationRun.status == RunStatus.RUNNING.value)
        .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
    )
    recovered: list[EvaluationRun] = []
    for row in list((await session.scalars(stmt)).all()):
        if row.lease_until is not None and row.lease_until > now:
            continue
        row.status = RunStatus.QUEUED.value
        row.interrupt_reason = "WORKER_CRASH"
        row.error_message = message
        row.lease_owner = None
        row.lease_until = None
        row.finished_at = None
        recovered.append(row)
    return recovered


async def list_queued_label_jobs(session: AsyncSession) -> list[EvaluationLabelJob]:
    """扫描全部排队的智能标注任务。执行前再读取任务行上的租户。"""
    stmt = (
        select(EvaluationLabelJob)
        .where(EvaluationLabelJob.status == LabelJobStatus.QUEUED.value)
        .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
    )
    return list((await session.scalars(stmt)).all())


async def requeue_stale_label_jobs(
    session: AsyncSession,
    message: str,
    *,
    stale_after: timedelta | None = None,
) -> list[EvaluationLabelJob]:
    """把 RUNNING 的标注任务改回 QUEUED。确认过程幂等，已确认的草稿不会重复写入。"""
    stmt = (
        select(EvaluationLabelJob)
        .where(EvaluationLabelJob.status == LabelJobStatus.RUNNING.value)
        .execution_options(**privileged_option(PrivilegedOperation.WORKER_CLAIM))
    )
    now = datetime.now(UTC)
    recovered: list[EvaluationLabelJob] = []
    for row in list((await session.scalars(stmt)).all()):
        if stale_after is not None and row.updated_at is not None and row.updated_at > now - stale_after:
            continue
        row.status = LabelJobStatus.QUEUED.value
        row.error_message = message
        row.finished_at = None
        recovered.append(row)
    return recovered
