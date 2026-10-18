from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import (
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

    async def list_experiments(self, *, dataset_id: int | None, page: int, page_size: int):
        tenant_id = self.ensure_tenant()
        filters = [EvaluationExperiment.tenant_id == tenant_id, EvaluationExperiment.deleted_at.is_(None)]
        if dataset_id is not None:
            filters.append(EvaluationExperiment.dataset_id == dataset_id)
        total = int(await self.session.scalar(select(func.count(EvaluationExperiment.id)).where(*filters)) or 0)
        stmt = (
            select(EvaluationExperiment)
            .where(*filters)
            .order_by(EvaluationExperiment.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_experiment(self, experiment_id: int) -> EvaluationExperiment | None:
        tenant_id = self.ensure_tenant()
        return await self.session.scalar(
            select(EvaluationExperiment).where(
                EvaluationExperiment.tenant_id == tenant_id,
                EvaluationExperiment.id == experiment_id,
                EvaluationExperiment.deleted_at.is_(None),
            )
        )

    async def list_runs(self, *, experiment_id: int | None, page: int, page_size: int):
        tenant_id = self.ensure_tenant()
        filters = [EvaluationRun.tenant_id == tenant_id]
        if experiment_id is not None:
            filters.append(EvaluationRun.experiment_id == experiment_id)
        total = int(await self.session.scalar(select(func.count(EvaluationRun.id)).where(*filters)) or 0)
        stmt = (
            select(EvaluationRun)
            .where(*filters)
            .order_by(EvaluationRun.id.desc())
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
        stmt = select(EvaluationRun).where(EvaluationRun.status == RunStatus.RUNNING.value)
        rows = list((await self.session.scalars(stmt)).all())
        now = datetime.now(UTC)
        for row in rows:
            row.status = RunStatus.FAILED.value
            row.error_message = message
            row.finished_at = now
        return rows

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
                        EvaluationRun.status.in_((RunStatus.QUEUED.value, RunStatus.RUNNING.value)),
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
            if run.status == RunStatus.QUEUED.value:
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
                EvaluationRun.status.in_((RunStatus.QUEUED.value, RunStatus.RUNNING.value)),
            )
        )
