from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Float, and_, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import (
    ACTIVE_RUN_STATUSES,
    EvaluationCase,
    EvaluationDataset,
    EvaluationDatasetVersion,
    EvaluationExperiment,
    EvaluationJudgment,
    EvaluationResult,
    EvaluationRun,
    RunStatus,
)
from app.repositories.base import BaseRepository


class EvaluationRepository(BaseRepository):
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        super().__init__(session, tenant_id)

    async def list_datasets(self, *, q: str | None, page: int, page_size: int):
        tenant_id = self.ensure_tenant()
        filters = [EvaluationDataset.tenant_id == tenant_id, EvaluationDataset.deleted_at.is_(None)]
        if q:
            filters.append(EvaluationDataset.name.ilike(f"%{q}%"))
        total = int(await self.session.scalar(select(func.count(EvaluationDataset.id)).where(*filters)) or 0)
        stmt = (
            select(EvaluationDataset)
            .where(*filters)
            .order_by(EvaluationDataset.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_dataset(self, dataset_id: int) -> EvaluationDataset | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationDataset).where(
                EvaluationDataset.tenant_id == tenant_id,
                EvaluationDataset.id == dataset_id,
                EvaluationDataset.deleted_at.is_(None),
            )
        )

    async def get_dataset_by_name(self, name: str, *, exclude_id: int | None = None) -> EvaluationDataset | None:
        tenant_id = self.ensure_tenant()
        filters = [
            EvaluationDataset.tenant_id == tenant_id,
            EvaluationDataset.name == name,
            EvaluationDataset.deleted_at.is_(None),
        ]
        if exclude_id is not None:
            filters.append(EvaluationDataset.id != exclude_id)
        return await self.session.scalar(select(EvaluationDataset).where(*filters))

    async def list_cases(
        self,
        dataset_id: int,
        *,
        status: str | None,
        q: str | None,
        page: int,
        page_size: int,
    ):
        tenant_id = self.ensure_tenant()
        filters = [
            EvaluationCase.tenant_id == tenant_id,
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.deleted_at.is_(None),
        ]
        if status:
            filters.append(EvaluationCase.annotation_status == status)
        if q:
            filters.append(EvaluationCase.question.ilike(f"%{q}%"))
        total = int(await self.session.scalar(select(func.count(EvaluationCase.id)).where(*filters)) or 0)
        stmt = (
            select(EvaluationCase)
            .where(*filters)
            .order_by(EvaluationCase.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def list_all_cases(self, dataset_id: int) -> list[EvaluationCase]:
        tenant_id = self.ensure_tenant()
        stmt = select(EvaluationCase).where(
            EvaluationCase.tenant_id == tenant_id,
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.deleted_at.is_(None),
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_case(self, case_id: int) -> EvaluationCase | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationCase).where(
                EvaluationCase.tenant_id == tenant_id,
                EvaluationCase.id == case_id,
                EvaluationCase.deleted_at.is_(None),
            )
        )

    async def get_case_by_external_key(self, dataset_id: int, external_key: str) -> EvaluationCase | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationCase).where(
                EvaluationCase.tenant_id == tenant_id,
                EvaluationCase.dataset_id == dataset_id,
                EvaluationCase.external_key == external_key,
                EvaluationCase.deleted_at.is_(None),
            )
        )

    async def list_judgments(self, case_id: int) -> list[EvaluationJudgment]:
        tenant_id = self.ensure_tenant()
        stmt = select(EvaluationJudgment).where(
            EvaluationJudgment.tenant_id == tenant_id,
            EvaluationJudgment.case_id == case_id,
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_judgments_for_dataset(self, dataset_id: int) -> list[EvaluationJudgment]:
        tenant_id = self.ensure_tenant()
        stmt = select(EvaluationJudgment).where(
            EvaluationJudgment.tenant_id == tenant_id,
            EvaluationJudgment.dataset_id == dataset_id,
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_judgment(self, judgment_id: int) -> EvaluationJudgment | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationJudgment).where(
                EvaluationJudgment.tenant_id == tenant_id,
                EvaluationJudgment.id == judgment_id,
            )
        )

    async def case_counts(self, dataset_ids: list[int]) -> dict[int, dict[str, int]]:
        if not dataset_ids:
            return {}
        tenant_id = self.ensure_tenant()
        stmt = (
            select(EvaluationCase.dataset_id, EvaluationCase.annotation_status, func.count())
            .where(
                EvaluationCase.tenant_id == tenant_id,
                EvaluationCase.dataset_id.in_(dataset_ids),
                EvaluationCase.deleted_at.is_(None),
            )
            .group_by(EvaluationCase.dataset_id, EvaluationCase.annotation_status)
        )
        result: dict[int, dict[str, int]] = {item: {"PENDING": 0, "LABELED": 0, "READY": 0, "total": 0} for item in dataset_ids}
        for dataset_id, status, count in (await self.session.execute(stmt)).all():
            bucket = result.setdefault(int(dataset_id), {"PENDING": 0, "LABELED": 0, "READY": 0, "total": 0})
            bucket[str(status)] = int(count)
            bucket["total"] += int(count)
        return result

    async def list_versions(self, dataset_id: int) -> list[EvaluationDatasetVersion]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(EvaluationDatasetVersion)
            .where(
                EvaluationDatasetVersion.tenant_id == tenant_id,
                EvaluationDatasetVersion.dataset_id == dataset_id,
            )
            .order_by(EvaluationDatasetVersion.version.desc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_version(self, dataset_id: int, version: int) -> EvaluationDatasetVersion | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationDatasetVersion).where(
                EvaluationDatasetVersion.tenant_id == tenant_id,
                EvaluationDatasetVersion.dataset_id == dataset_id,
                EvaluationDatasetVersion.version == version,
            )
        )

    async def get_dataset_for_update(self, dataset_id: int) -> EvaluationDataset | None:
        """锁住数据集行，使冻结、开跑和删除快照按同一顺序排队。"""
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationDataset)
            .where(
                EvaluationDataset.tenant_id == tenant_id,
                EvaluationDataset.id == dataset_id,
                EvaluationDataset.deleted_at.is_(None),
            )
            .with_for_update()
        )

    async def get_version_for_update(self, dataset_id: int, version: int) -> EvaluationDatasetVersion | None:
        """锁住指定快照。必须先锁数据集，避免和开跑互相等待。"""
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationDatasetVersion)
            .where(
                EvaluationDatasetVersion.tenant_id == tenant_id,
                EvaluationDatasetVersion.dataset_id == dataset_id,
                EvaluationDatasetVersion.version == version,
            )
            .with_for_update()
        )

    async def list_versions_page(self, dataset_id: int, *, page: int, page_size: int) -> tuple[list[EvaluationDatasetVersion], int]:
        tenant_id = self.ensure_tenant()
        filters = [
            EvaluationDatasetVersion.tenant_id == tenant_id,
            EvaluationDatasetVersion.dataset_id == dataset_id,
        ]
        total = int(await self.session.scalar(select(func.count(EvaluationDatasetVersion.id)).where(*filters)) or 0)
        stmt = (
            select(EvaluationDatasetVersion)
            .where(*filters)
            .order_by(EvaluationDatasetVersion.version.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def count_runs_for_version(self, dataset_id: int, version: int) -> int:
        tenant_id = self.ensure_tenant()
        return int(
            await self.session.scalar(
                select(func.count(EvaluationRun.id)).where(
                    EvaluationRun.tenant_id == tenant_id,
                    EvaluationRun.dataset_id == dataset_id,
                    EvaluationRun.dataset_version == version,
                )
            )
            or 0
        )

    async def run_counts_by_version(self, dataset_id: int) -> dict[int, int]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(EvaluationRun.dataset_version, func.count())
            .where(
                EvaluationRun.tenant_id == tenant_id,
                EvaluationRun.dataset_id == dataset_id,
            )
            .group_by(EvaluationRun.dataset_version)
        )
        return {int(version): int(count) for version, count in (await self.session.execute(stmt)).all()}

    async def list_experiments(
        self,
        *,
        dataset_id: int | None,
        status: str | None,
        strategy: str | None,
        sort_by: str,
        sort_order: str,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[EvaluationExperiment, EvaluationRun | None]], int]:
        """按最近一次运行做筛选排序，避免列表再逐条查 run。"""
        tenant_id = self.ensure_tenant()
        latest_run_id = (
            select(func.max(EvaluationRun.id))
            .where(
                EvaluationRun.tenant_id == tenant_id,
                EvaluationRun.experiment_id == EvaluationExperiment.id,
            )
            .correlate(EvaluationExperiment)
            .scalar_subquery()
        )
        filters = [EvaluationExperiment.tenant_id == tenant_id, EvaluationExperiment.deleted_at.is_(None)]
        if dataset_id is not None:
            filters.append(EvaluationExperiment.dataset_id == dataset_id)
        if strategy:
            filters.append(EvaluationExperiment.config["strategy"].astext == strategy)
        if status == "NEVER_RUN":
            filters.append(EvaluationRun.id.is_(None))
        elif status:
            filters.append(EvaluationRun.status == status)

        join_on = and_(EvaluationRun.tenant_id == tenant_id, EvaluationRun.id == latest_run_id)
        count_stmt = (
            select(func.count(EvaluationExperiment.id))
            .select_from(EvaluationExperiment)
            .outerjoin(EvaluationRun, join_on)
            .where(*filters)
        )
        total = int(await self.session.scalar(count_stmt) or 0)

        metric_cols = {
            "recall": EvaluationRun.metrics["recall"].astext.cast(Float),
            "mrr": EvaluationRun.metrics["mrr"].astext.cast(Float),
            "ndcg": EvaluationRun.metrics["ndcg"].astext.cast(Float),
            "hit_rate": EvaluationRun.metrics["hit_rate"].astext.cast(Float),
            "latency_p95": EvaluationRun.usage["latency_p95_ms"].astext.cast(Float),
            "id": EvaluationExperiment.id,
            "created_at": EvaluationExperiment.created_at,
        }
        order_col = metric_cols.get(sort_by, EvaluationExperiment.id)
        order_expr = order_col.asc() if sort_order == "asc" else order_col.desc()
        stmt = (
            select(EvaluationExperiment, EvaluationRun)
            .outerjoin(EvaluationRun, join_on)
            .where(*filters)
            .order_by(nulls_last(order_expr), EvaluationExperiment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await self.session.execute(stmt)).all())
        return [(experiment, run) for experiment, run in rows], total

    async def get_experiment(self, experiment_id: int) -> EvaluationExperiment | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationExperiment).where(
                EvaluationExperiment.tenant_id == tenant_id,
                EvaluationExperiment.id == experiment_id,
                EvaluationExperiment.deleted_at.is_(None),
            )
        )

    async def list_runs(
        self,
        *,
        experiment_id: int | None,
        status: str | None = None,
        strategy: str | None = None,
        sort_by: str = "id",
        sort_order: str = "desc",
        page: int,
        page_size: int,
    ):
        tenant_id = self.ensure_tenant()
        filters = [EvaluationRun.tenant_id == tenant_id]
        if experiment_id is not None:
            filters.append(EvaluationRun.experiment_id == experiment_id)
        if status:
            filters.append(EvaluationRun.status == status)
        if strategy:
            filters.append(EvaluationRun.config_snapshot["strategy"].astext == strategy)
        total = int(await self.session.scalar(select(func.count(EvaluationRun.id)).where(*filters)) or 0)
        metric_cols = {
            "recall": EvaluationRun.metrics["recall"].astext.cast(Float),
            "mrr": EvaluationRun.metrics["mrr"].astext.cast(Float),
            "ndcg": EvaluationRun.metrics["ndcg"].astext.cast(Float),
            "hit_rate": EvaluationRun.metrics["hit_rate"].astext.cast(Float),
            "latency_p95": EvaluationRun.usage["latency_p95_ms"].astext.cast(Float),
            "id": EvaluationRun.id,
            "created_at": EvaluationRun.created_at,
        }
        order_col = metric_cols.get(sort_by, EvaluationRun.id)
        order_expr = order_col.asc() if sort_order == "asc" else order_col.desc()
        stmt = (
            select(EvaluationRun)
            .where(*filters)
            .order_by(nulls_last(order_expr), EvaluationRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_run(self, run_id: int) -> EvaluationRun | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationRun).where(EvaluationRun.tenant_id == tenant_id, EvaluationRun.id == run_id)
        )

    async def get_run_for_update(self, run_id: int) -> EvaluationRun | None:
        return await self.session.scalar(
            select(EvaluationRun).where(EvaluationRun.id == run_id).with_for_update()
        )

    async def list_results(self, run_id: int) -> list[EvaluationResult]:
        tenant_id = self.ensure_tenant()
        stmt = (
            select(EvaluationResult)
            .where(EvaluationResult.tenant_id == tenant_id, EvaluationResult.run_id == run_id)
            .order_by(EvaluationResult.id.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_result_by_run_case(self, run_id: int, case_id: int) -> EvaluationResult | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationResult).where(
                EvaluationResult.tenant_id == tenant_id,
                EvaluationResult.run_id == run_id,
                EvaluationResult.case_id == case_id,
            )
        )

    async def get_result(self, result_id: int) -> EvaluationResult | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationResult).where(
                EvaluationResult.tenant_id == tenant_id,
                EvaluationResult.id == result_id,
            )
        )

    async def delete_results(self, run_id: int) -> None:
        tenant_id = self.ensure_tenant()
        rows = await self.list_results(run_id)
        for row in rows:
            if row.tenant_id == tenant_id:
                await self.session.delete(row)

    async def fail_stale_running(self, message: str) -> list[EvaluationRun]:
        """兼容旧 Worker：评测改走 pause_stale_running，保留部分结果。"""
        return await self.pause_stale_running(message)

    async def pause_stale_running(self, message: str) -> list[EvaluationRun]:
        """把租约已过期或未持有租约的 RUNNING 标为 QUEUED，保留已落库题目。

        仍在租约窗口内的任务可能由其他 Worker 执行，不能抢。
        """
        now = datetime.now(UTC)
        stmt = select(EvaluationRun).where(EvaluationRun.status == RunStatus.RUNNING.value)
        recovered: list[EvaluationRun] = []
        for row in list((await self.session.scalars(stmt)).all()):
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

    async def list_queued_runs(self) -> list[EvaluationRun]:
        stmt = select(EvaluationRun).where(EvaluationRun.status == RunStatus.QUEUED.value)
        return list((await self.session.scalars(stmt)).all())

    async def request_cancel_for_knowledge_base(self, knowledge_base_id: int) -> int:
        """知识库删除后取消仍覆盖该库的排队/运行中评测。历史结果与快照保留。"""
        tenant_id = self.ensure_tenant()
        rows = list(
            (
                await self.session.scalars(
                    select(EvaluationRun).where(
                        EvaluationRun.tenant_id == tenant_id,
                        EvaluationRun.status.in_(ACTIVE_RUN_STATUSES),
                    )
                )
            ).all()
        )
        now = datetime.now(UTC)
        count = 0
        for run in rows:
            ids = list((run.config_snapshot or {}).get("knowledge_base_ids") or [])
            if ids and knowledge_base_id not in ids:
                continue
            if not ids:
                continue
            run.cancel_requested = True
            run.error_message = "知识库已删除，评测取消"
            if run.status in {RunStatus.QUEUED.value, RunStatus.PAUSED.value}:
                run.status = RunStatus.CANCELLED.value
                run.finished_at = now
            count += 1
        return count

    async def find_active_run(self, experiment_id: int) -> EvaluationRun | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationRun).where(
                EvaluationRun.tenant_id == tenant_id,
                EvaluationRun.experiment_id == experiment_id,
                EvaluationRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        )
