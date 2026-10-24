from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import (
    AgentEvaluationCase,
    AgentEvaluationCaseRun,
    AgentEvaluationComparison,
    AgentEvaluationDataset,
    AgentEvaluationDatasetVersion,
    AgentEvaluationRun,
    AgentEvaluationRunEvent,
)


class AgentEvaluationRepository:
    """所有用户 API 查询同时绑定 tenant_id 和 user_id；Worker 使用独立受控入口。"""

    def __init__(self, session: AsyncSession, tenant_id: int, user_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def create_dataset(self, name: str, description: str | None) -> AgentEvaluationDataset:
        row = AgentEvaluationDataset(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            name=name,
            description=description,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def dataset(
        self, dataset_id: int, *, lock: bool = False
    ) -> AgentEvaluationDataset | None:
        stmt = select(AgentEvaluationDataset).where(
            AgentEvaluationDataset.tenant_id == self.tenant_id,
            AgentEvaluationDataset.user_id == self.user_id,
            AgentEvaluationDataset.id == dataset_id,
        )
        return await self.session.scalar(stmt.with_for_update() if lock else stmt)

    async def datasets(self, page: int, page_size: int) -> tuple[list[AgentEvaluationDataset], int]:
        filters = (
            AgentEvaluationDataset.tenant_id == self.tenant_id,
            AgentEvaluationDataset.user_id == self.user_id,
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(AgentEvaluationDataset).where(*filters)
            )
            or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    select(AgentEvaluationDataset)
                    .where(*filters)
                    .order_by(AgentEvaluationDataset.updated_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, total

    async def case(self, case_id: int) -> AgentEvaluationCase | None:
        return await self.session.scalar(
            select(AgentEvaluationCase)
            .join(
                AgentEvaluationDataset, AgentEvaluationDataset.id == AgentEvaluationCase.dataset_id
            )
            .where(
                AgentEvaluationCase.tenant_id == self.tenant_id,
                AgentEvaluationCase.id == case_id,
                AgentEvaluationDataset.tenant_id == self.tenant_id,
                AgentEvaluationDataset.user_id == self.user_id,
            )
        )

    async def cases(self, dataset_id: int) -> list[AgentEvaluationCase]:
        return list(
            (
                await self.session.scalars(
                    select(AgentEvaluationCase)
                    .where(
                        AgentEvaluationCase.tenant_id == self.tenant_id,
                        AgentEvaluationCase.dataset_id == dataset_id,
                    )
                    .order_by(AgentEvaluationCase.id)
                )
            ).all()
        )

    async def versions(self, dataset_id: int) -> list[AgentEvaluationDatasetVersion]:
        return list(
            (
                await self.session.scalars(
                    select(AgentEvaluationDatasetVersion)
                    .where(
                        AgentEvaluationDatasetVersion.tenant_id == self.tenant_id,
                        AgentEvaluationDatasetVersion.user_id == self.user_id,
                        AgentEvaluationDatasetVersion.dataset_id == dataset_id,
                    )
                    .order_by(AgentEvaluationDatasetVersion.version.desc())
                )
            ).all()
        )

    async def version(self, version_id: int) -> AgentEvaluationDatasetVersion | None:
        return await self.session.scalar(
            select(AgentEvaluationDatasetVersion).where(
                AgentEvaluationDatasetVersion.tenant_id == self.tenant_id,
                AgentEvaluationDatasetVersion.user_id == self.user_id,
                AgentEvaluationDatasetVersion.id == version_id,
            )
        )

    async def run(self, run_id: int, *, lock: bool = False) -> AgentEvaluationRun | None:
        stmt = select(AgentEvaluationRun).where(
            AgentEvaluationRun.tenant_id == self.tenant_id,
            AgentEvaluationRun.user_id == self.user_id,
            AgentEvaluationRun.id == run_id,
        )
        return await self.session.scalar(stmt.with_for_update() if lock else stmt)

    async def runs(self, page: int, page_size: int) -> tuple[list[AgentEvaluationRun], int]:
        filters = (
            AgentEvaluationRun.tenant_id == self.tenant_id,
            AgentEvaluationRun.user_id == self.user_id,
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(AgentEvaluationRun).where(*filters)
            )
            or 0
        )
        rows = list(
            (
                await self.session.scalars(
                    select(AgentEvaluationRun)
                    .where(*filters)
                    .order_by(AgentEvaluationRun.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return rows, total

    async def case_runs(self, run_id: int) -> list[AgentEvaluationCaseRun]:
        return list(
            (
                await self.session.scalars(
                    select(AgentEvaluationCaseRun)
                    .where(
                        AgentEvaluationCaseRun.tenant_id == self.tenant_id,
                        AgentEvaluationCaseRun.run_id == run_id,
                    )
                    .order_by(AgentEvaluationCaseRun.id)
                )
            ).all()
        )

    async def comparison(self, comparison_id: int) -> AgentEvaluationComparison | None:
        return await self.session.scalar(
            select(AgentEvaluationComparison).where(
                AgentEvaluationComparison.tenant_id == self.tenant_id,
                AgentEvaluationComparison.user_id == self.user_id,
                AgentEvaluationComparison.id == comparison_id,
            )
        )

    async def acquire_run(
        self, run_id: int, owner: str, lease_seconds: int
    ) -> AgentEvaluationRun | None:
        """通过条件 UPDATE 领取租约，避免两个 Worker 同时执行一个 Run。"""
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(AgentEvaluationRun)
            .where(
                AgentEvaluationRun.tenant_id == self.tenant_id,
                AgentEvaluationRun.user_id == self.user_id,
                AgentEvaluationRun.id == run_id,
                AgentEvaluationRun.status.in_(("QUEUED", "RUNNING", "PAUSED")),
                or_(
                    AgentEvaluationRun.lease_until.is_(None),
                    AgentEvaluationRun.lease_until <= now,
                    AgentEvaluationRun.lease_owner == owner,
                ),
            )
            .values(lease_owner=owner, lease_until=now + timedelta(seconds=lease_seconds))
        )
        if int(getattr(result, "rowcount", 0) or 0) == 0:
            return None
        return await self.run(run_id, lock=True)

    async def event(self, run_id: int, event_type: str, detail: dict | None = None) -> None:
        self.session.add(
            AgentEvaluationRunEvent(
                tenant_id=self.tenant_id, run_id=run_id, event_type=event_type, detail=detail or {}
            )
        )
