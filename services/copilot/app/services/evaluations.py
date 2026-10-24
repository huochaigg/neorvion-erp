from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.evaluation.metrics import aggregate_metrics, compare_runs, evaluate_case
from app.models.evaluation import (
    AgentEvaluationCase,
    AgentEvaluationCaseRun,
    AgentEvaluationComparison,
    AgentEvaluationDatasetVersion,
    AgentEvaluationRun,
)
from app.repositories.evaluations import AgentEvaluationRepository
from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseImport,
    EvaluationCaseOut,
    EvaluationCasePatch,
    EvaluationCaseRunOut,
    EvaluationComparisonCreate,
    EvaluationComparisonOut,
    EvaluationDatasetCreate,
    EvaluationDatasetDetailOut,
    EvaluationDatasetOut,
    EvaluationDatasetPatch,
    EvaluationDatasetVersionOut,
    EvaluationHumanReview,
    EvaluationRunCreate,
    EvaluationRunDetailOut,
    EvaluationRunOut,
)


class AgentEvaluationService:
    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context
        self.repo = AgentEvaluationRepository(session, context.tenant_id, context.user_id)

    async def create_dataset(self, payload: EvaluationDatasetCreate) -> EvaluationDatasetOut:
        try:
            row = await self.repo.create_dataset(payload.name, payload.description)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("同名评测数据集已存在", code=40990, status_code=409) from exc
        return EvaluationDatasetOut.model_validate(row, from_attributes=True)

    async def list_datasets(self, page: int, page_size: int) -> dict:
        rows, total = await self.repo.datasets(page, page_size)
        return {
            "items": [EvaluationDatasetOut.model_validate(x, from_attributes=True) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def dataset_detail(self, dataset_id: int) -> EvaluationDatasetDetailOut:
        row = await self._dataset(dataset_id)
        cases = await self.repo.cases(dataset_id)
        return EvaluationDatasetDetailOut(
            **EvaluationDatasetOut.model_validate(row, from_attributes=True).model_dump(),
            cases=[EvaluationCaseOut.model_validate(x, from_attributes=True) for x in cases],
        )

    async def patch_dataset(
        self, dataset_id: int, payload: EvaluationDatasetPatch
    ) -> EvaluationDatasetOut:
        row = await self._dataset(dataset_id, lock=True)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by = self.context.user_id
        await self.session.commit()
        return EvaluationDatasetOut.model_validate(row, from_attributes=True)

    async def add_case(self, dataset_id: int, payload: EvaluationCaseCreate) -> EvaluationCaseOut:
        await self._dataset(dataset_id)
        row = AgentEvaluationCase(
            tenant_id=self.context.tenant_id,
            dataset_id=dataset_id,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
            **payload.model_dump(),
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Case external_key 已存在", code=40991, status_code=409) from exc
        return EvaluationCaseOut.model_validate(row, from_attributes=True)

    async def import_cases(self, dataset_id: int, payload: EvaluationCaseImport) -> dict:
        """批量导入以 external_key 幂等；已存在条目不被静默改写。"""
        await self._dataset(dataset_id)
        existing = {item.external_key for item in await self.repo.cases(dataset_id)}
        inserted = 0
        skipped = 0
        for item in payload.items:
            if item.external_key in existing:
                skipped += 1
                continue
            self.session.add(
                AgentEvaluationCase(
                    tenant_id=self.context.tenant_id,
                    dataset_id=dataset_id,
                    created_by=self.context.user_id,
                    updated_by=self.context.user_id,
                    **item.model_dump(),
                )
            )
            existing.add(item.external_key)
            inserted += 1
        await self.session.commit()
        return {"inserted": inserted, "skipped": skipped}

    async def import_v8_baseline(self, dataset_id: int) -> dict:
        """将仓库内已验证的 V8 路由 Case 转换为结构化 V9 Case，不生成自由文本标准答案。"""
        source = Path(__file__).resolve().parents[2] / "evals" / "v8_cases.json"
        rows = json.loads(source.read_text(encoding="utf-8"))
        payload = EvaluationCaseImport(
            items=[
                EvaluationCaseCreate(
                    external_key=f"v8-{item['id']}",
                    case_type=str(item["category"]),
                    difficulty=2,
                    user_input=str(item["query"]),
                    expected_behavior={"expected_mode": item["expected_mode"]},
                    expected_tools={
                        "required": [],
                        "optional": [],
                        "forbidden": [
                            "execute_action",
                            "create_purchase_order",
                            "adjust_inventory",
                        ],
                    },
                    forbidden_actions=["ERP_WRITE", "AUTO_APPROVE"],
                    required_permissions=["copilot:use"],
                    scenario_config={"source": "v8_cases.json"},
                    status="READY",
                )
                for item in rows
            ]
        )
        return await self.import_cases(dataset_id, payload)

    async def import_v9_catalog(self, dataset_id: int) -> dict:
        """幂等导入仓库内 V9-AGENT-100；保留每题真实的审核状态与结构化断言。"""
        source = Path(__file__).resolve().parents[2] / "evals" / "v9_agent_100.json"
        rows = json.loads(source.read_text(encoding="utf-8"))
        payload = EvaluationCaseImport(items=[EvaluationCaseCreate.model_validate(x) for x in rows])
        result = await self.import_cases(dataset_id, payload)
        result.update(
            {
                "catalog": "V9-AGENT-100",
                "ready": sum(x.get("status") == "READY" for x in rows),
                "needs_review": sum(x.get("status") == "NEEDS_REVIEW" for x in rows),
            }
        )
        return result

    async def patch_case(self, case_id: int, payload: EvaluationCasePatch) -> EvaluationCaseOut:
        row = await self.repo.case(case_id)
        if row is None:
            raise AppError("评测 Case 不存在", code=40490, status_code=404)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by = self.context.user_id
        await self.session.commit()
        return EvaluationCaseOut.model_validate(row, from_attributes=True)

    async def delete_case(self, case_id: int) -> None:
        row = await self.repo.case(case_id)
        if row is None:
            raise AppError("评测 Case 不存在", code=40490, status_code=404)
        await self.session.delete(row)
        await self.session.commit()

    async def freeze(self, dataset_id: int) -> EvaluationDatasetVersionOut:
        """在同一事务锁定数据集并保存规范化 JSON 快照，后续草稿编辑不会影响版本。"""
        dataset = await self._dataset(dataset_id, lock=True)
        cases = await self.repo.cases(dataset_id)
        enabled = [item for item in cases if item.status != "DISABLED"]
        snapshot = [self._case_snapshot(item) for item in enabled]
        canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        ready = sum(item["status"] == "READY" for item in snapshot)
        version = dataset.current_version + 1
        row = AgentEvaluationDatasetVersion(
            tenant_id=self.context.tenant_id,
            dataset_id=dataset.id,
            user_id=self.context.user_id,
            version=version,
            snapshot=snapshot,
            content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            case_count=len(snapshot),
            ready_count=ready,
            review_count=len(snapshot) - ready,
            frozen_by=self.context.user_id,
        )
        dataset.current_version = version
        dataset.status = "ACTIVE"
        self.session.add(row)
        await self.session.commit()
        return EvaluationDatasetVersionOut.model_validate(row, from_attributes=True)

    async def versions(self, dataset_id: int) -> list[EvaluationDatasetVersionOut]:
        await self._dataset(dataset_id)
        return [
            EvaluationDatasetVersionOut.model_validate(x, from_attributes=True)
            for x in await self.repo.versions(dataset_id)
        ]

    async def create_run(self, payload: EvaluationRunCreate) -> EvaluationRunOut:
        version = await self.repo.version(payload.dataset_version_id)
        if version is None:
            raise AppError("冻结版本不存在", code=40491, status_code=404)
        if payload.execution_kind == "LIVE":
            raise AppError(
                "LIVE 评测尚未接入受控服务身份与只读执行器，当前仅允许 REPLAY",
                code=40390,
                status_code=403,
            )
        ready = [item for item in version.snapshot if item.get("status") == "READY"]
        if not ready:
            raise AppError("冻结版本没有已审核 READY Case", code=40090, status_code=400)
        config = {
            **payload.config,
            "dataset_content_hash": version.content_hash,
            "agent_registry_version": "v8.1",
            "tool_registry_version": "v4",
            "prompt_version": "v8",
            "safety_write_tools": False,
        }
        fingerprint = hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode()
        ).hexdigest()
        row = AgentEvaluationRun(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            dataset_version_id=version.id,
            comparison_group=payload.comparison_group,
            idempotency_key=payload.idempotency_key,
            mode=payload.mode,
            execution_kind=payload.execution_kind,
            model_provider=settings.model_provider,
            model_name=settings.chat_model,
            config_snapshot=config,
            environment_fingerprint=fingerprint,
            total_cases=len(ready),
            token_budget=payload.token_budget,
            cost_budget=payload.cost_budget,
        )
        self.session.add(row)
        try:
            await self.session.flush()
            for item in ready:
                self.session.add(
                    AgentEvaluationCaseRun(
                        tenant_id=self.context.tenant_id,
                        run_id=row.id,
                        case_key=str(item["external_key"]),
                    )
                )
            await self.repo.event(
                row.id, "RUN_QUEUED", {"mode": row.mode, "execution_kind": row.execution_kind}
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.scalar(
                select(AgentEvaluationRun).where(
                    AgentEvaluationRun.tenant_id == self.context.tenant_id,
                    AgentEvaluationRun.user_id == self.context.user_id,
                    AgentEvaluationRun.idempotency_key == payload.idempotency_key,
                )
            )
            if existing is None:
                raise
            row = existing
        return EvaluationRunOut.model_validate(row, from_attributes=True)

    async def list_runs(self, page: int, page_size: int) -> dict:
        rows, total = await self.repo.runs(page, page_size)
        return {
            "items": [EvaluationRunOut.model_validate(x, from_attributes=True) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def run_detail(self, run_id: int) -> EvaluationRunDetailOut:
        row = await self._run(run_id)
        cases = await self.repo.case_runs(run_id)
        return EvaluationRunDetailOut(
            **EvaluationRunOut.model_validate(row, from_attributes=True).model_dump(),
            cases=[EvaluationCaseRunOut.model_validate(x, from_attributes=True) for x in cases],
        )

    async def pause(self, run_id: int) -> EvaluationRunOut:
        row = await self._run(run_id, lock=True)
        if row.status not in {"QUEUED", "RUNNING"}:
            raise AppError("当前状态不能暂停", code=40992, status_code=409)
        row.pause_requested = True
        row.status = "PAUSING" if row.status == "RUNNING" else "PAUSED"
        await self.repo.event(row.id, "RUN_PAUSE_REQUESTED")
        await self.session.commit()
        return EvaluationRunOut.model_validate(row, from_attributes=True)

    async def resume(self, run_id: int) -> EvaluationRunOut:
        row = await self._run(run_id, lock=True)
        if row.status not in {"PAUSED", "PARTIAL_FAILED", "FAILED"}:
            raise AppError("当前状态不能恢复", code=40993, status_code=409)
        row.pause_requested = False
        row.cancel_requested = False
        row.status = "QUEUED"
        row.lease_owner = None
        row.lease_until = None
        await self.repo.event(row.id, "RUN_RESUMED")
        await self.session.commit()
        return EvaluationRunOut.model_validate(row, from_attributes=True)

    async def cancel(self, run_id: int) -> EvaluationRunOut:
        row = await self._run(run_id, lock=True)
        if row.status in {"SUCCEEDED", "CANCELLED"}:
            return EvaluationRunOut.model_validate(row, from_attributes=True)
        row.cancel_requested = True
        if row.status in {"QUEUED", "PAUSED", "FAILED", "PARTIAL_FAILED"}:
            row.status = "CANCELLED"
            row.finished_at = datetime.now(UTC)
        await self.repo.event(row.id, "RUN_CANCEL_REQUESTED")
        await self.session.commit()
        return EvaluationRunOut.model_validate(row, from_attributes=True)

    async def metrics(self, run_id: int) -> dict:
        row = await self._run(run_id)
        case_runs = await self.repo.case_runs(run_id)
        computed = aggregate_metrics(
            [
                {"task_outcome": x.task_outcome, "metrics": x.metrics}
                for x in case_runs
                if x.status in {"SUCCEEDED", "FAILED", "SKIPPED"}
            ]
        )
        return {"run_id": row.id, "stored": row.metrics, "recomputed": computed}

    async def review_case(
        self, run_id: int, case_run_id: int, payload: EvaluationHumanReview
    ) -> EvaluationCaseRunOut:
        """人工可覆核开放式结论，但不能覆盖已经发生的不安全执行。"""
        run = await self._run(run_id)
        row = await self.session.scalar(
            select(AgentEvaluationCaseRun).where(
                AgentEvaluationCaseRun.tenant_id == self.context.tenant_id,
                AgentEvaluationCaseRun.run_id == run_id,
                AgentEvaluationCaseRun.id == case_run_id,
            )
        )
        if row is None:
            raise AppError("CaseRun 不存在", code=40493, status_code=404)
        if int((row.metrics or {}).get("unsafe_action_executions") or 0) > 0:
            raise AppError("人工覆核不能覆盖不安全执行失败", code=40995, status_code=409)
        row.human_override = {
            "outcome": payload.outcome,
            "rationale": payload.rationale,
            "reviewed_by": self.context.user_id,
            "reviewed_at": datetime.now(UTC).isoformat(),
        }
        row.task_outcome = payload.outcome
        all_rows = await self.repo.case_runs(run_id)
        run.metrics = aggregate_metrics(
            [
                {"task_outcome": item.task_outcome, "metrics": item.metrics}
                for item in all_rows
                if item.status in {"SUCCEEDED", "FAILED", "SKIPPED"}
            ]
        )
        await self.session.commit()
        return EvaluationCaseRunOut.model_validate(row, from_attributes=True)

    async def compare(self, payload: EvaluationComparisonCreate) -> EvaluationComparisonOut:
        baseline = await self._run(payload.baseline_run_id)
        candidate = await self._run(payload.candidate_run_id)
        terminal = {"SUCCEEDED", "PARTIAL_FAILED", "FAILED"}
        if baseline.status not in terminal or candidate.status not in terminal:
            raise AppError("只有已终态 Run 可以生成对比报告", code=40994, status_code=409)
        same_version = baseline.dataset_version_id == candidate.dataset_version_id
        same_environment = baseline.environment_fingerprint == candidate.environment_fingerprint
        comparable = same_version and same_environment
        reason = None if comparable else "冻结版本或环境 fingerprint 不一致"
        report = compare_runs(
            [
                {"case_key": x.case_key, "task_outcome": x.task_outcome, "metrics": x.metrics}
                for x in await self.repo.case_runs(baseline.id)
            ],
            [
                {"case_key": x.case_key, "task_outcome": x.task_outcome, "metrics": x.metrics}
                for x in await self.repo.case_runs(candidate.id)
            ],
        )
        report["strictly_comparable"] = comparable
        report["sample_stability"] = "LOW_SAMPLE" if report["paired_cases"] < 30 else "STABLE"
        report["thresholds"] = {
            "task_success_drop": settings.evaluation_task_success_regression_threshold,
            "latency_increase": settings.evaluation_latency_regression_threshold,
            "token_increase": settings.evaluation_token_regression_threshold,
            "unsafe_execution": 0,
        }
        report["alerts"] = self._comparison_alerts(report) if comparable else []
        row = AgentEvaluationComparison(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            baseline_run_id=baseline.id,
            candidate_run_id=candidate.id,
            comparable=comparable,
            incomparable_reason=reason,
            report=report,
        )
        self.session.add(row)
        await self.session.commit()
        return EvaluationComparisonOut.model_validate(row, from_attributes=True)

    @staticmethod
    def _comparison_alerts(report: dict[str, Any]) -> list[dict[str, Any]]:
        """按项目阈值生成报警，只描述指标相关性，不臆断某次 Prompt 修改是根因。"""
        alerts: list[dict[str, Any]] = []
        left = report["baseline_metrics"]
        right = report["candidate_metrics"]
        before = left["task_success_rate"]["value"]
        after = right["task_success_rate"]["value"]
        if (
            before is not None
            and after is not None
            and before - after > settings.evaluation_task_success_regression_threshold
        ):
            alerts.append(
                {
                    "metric": "task_success_rate",
                    "severity": "WARNING",
                    "delta": after - before,
                }
            )
        unsafe = right["unsafe_action_execution_rate"]["value"]
        if unsafe is not None and unsafe > 0:
            alerts.append(
                {
                    "metric": "unsafe_action_execution_rate",
                    "severity": "BLOCKER",
                    "value": unsafe,
                }
            )
        before_latency = left.get("latency_p95_ms")
        after_latency = right.get("latency_p95_ms")
        if (
            before_latency
            and after_latency
            and (after_latency - before_latency) / before_latency
            > settings.evaluation_latency_regression_threshold
        ):
            alerts.append(
                {
                    "metric": "latency_p95_ms",
                    "severity": "INFO",
                    "delta": after_latency - before_latency,
                }
            )
        before_tokens = left.get("input_tokens")
        after_tokens = right.get("input_tokens")
        if (
            before_tokens
            and after_tokens
            and (after_tokens - before_tokens) / before_tokens
            > settings.evaluation_token_regression_threshold
        ):
            alerts.append(
                {
                    "metric": "input_tokens",
                    "severity": "INFO",
                    "delta": after_tokens - before_tokens,
                }
            )
        return alerts

    async def comparison(self, comparison_id: int) -> EvaluationComparisonOut:
        row = await self.repo.comparison(comparison_id)
        if row is None:
            raise AppError("对比报告不存在", code=40492, status_code=404)
        return EvaluationComparisonOut.model_validate(row, from_attributes=True)

    async def _dataset(self, dataset_id: int, *, lock: bool = False):
        row = await self.repo.dataset(dataset_id, lock=lock)
        if row is None:
            raise AppError("评测数据集不存在", code=40490, status_code=404)
        return row

    async def _run(self, run_id: int, *, lock: bool = False):
        row = await self.repo.run(run_id, lock=lock)
        if row is None:
            raise AppError("评测 Run 不存在", code=40491, status_code=404)
        return row

    @staticmethod
    def _case_snapshot(row: AgentEvaluationCase) -> dict[str, Any]:
        return {
            "id": row.id,
            "external_key": row.external_key,
            "case_type": row.case_type,
            "difficulty": row.difficulty,
            "user_input": row.user_input,
            "expected_behavior": row.expected_behavior,
            "expected_tools": row.expected_tools,
            "expected_arguments": row.expected_arguments,
            "expected_evidence": row.expected_evidence,
            "expected_answer_assertions": row.expected_answer_assertions,
            "forbidden_actions": row.forbidden_actions,
            "required_permissions": row.required_permissions,
            "scenario_config": row.scenario_config,
            "status": row.status,
        }


class ReplayEvaluationRunner:
    """安全执行冻结 Replay；绝不调用 Proposal、Execution、Workflow 或 ERP 写接口。"""

    def __init__(self, session: AsyncSession, tenant_id: int, user_id: int, owner: str) -> None:
        self.session = session
        self.repo = AgentEvaluationRepository(session, tenant_id, user_id)
        self.owner = owner

    async def execute(self, run_id: int) -> bool:
        run = await self.repo.acquire_run(run_id, self.owner, settings.evaluation_lease_seconds)
        if run is None:
            await self.session.rollback()
            return False
        version = await self.repo.version(run.dataset_version_id)
        if version is None:
            run.status = "FAILED"
            await self.session.commit()
            return False
        run.status = "RUNNING"
        run.started_at = run.started_at or datetime.now(UTC)
        snapshots = {str(x["external_key"]): x for x in version.snapshot}
        await self.repo.event(run.id, "RUN_STARTED", {"owner": self.owner})
        await self.session.commit()
        used_tokens = 0
        used_cost = 0.0
        for existing in await self.repo.case_runs(run.id):
            values = existing.metrics or {}
            if existing.status not in {"SUCCEEDED", "FAILED"}:
                continue
            if values.get("input_tokens") is not None and values.get("output_tokens") is not None:
                used_tokens += int(values["input_tokens"]) + int(values["output_tokens"])
            if values.get("estimated_cost") is not None:
                used_cost += float(values["estimated_cost"])
        for case_run in await self.repo.case_runs(run.id):
            await self.session.refresh(run)
            if run.cancel_requested:
                run.status = "CANCELLED"
                break
            if run.pause_requested:
                run.status = "PAUSED"
                break
            if case_run.status == "SUCCEEDED":
                continue
            case = snapshots.get(case_run.case_key)
            if not case:
                case_run.status = "FAILED"
                case_run.error_code = 40493
                continue
            scenario = case.get("scenario_config") or {}
            result = (scenario.get("replay_by_mode") or {}).get(run.mode) or scenario.get(
                "replay_result"
            )
            if isinstance(result, dict):
                usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
                next_tokens = (
                    int(usage["input_tokens"]) + int(usage["output_tokens"])
                    if usage.get("input_tokens") is not None
                    and usage.get("output_tokens") is not None
                    else 0
                )
                next_cost = float(result.get("estimated_cost") or 0)
                if run.token_budget is not None and used_tokens + next_tokens > run.token_budget:
                    run.status = "PAUSED"
                    run.pause_requested = True
                    await self.repo.event(run.id, "RUN_BUDGET_PAUSED", {"budget": "token"})
                    break
                if run.cost_budget is not None and used_cost + next_cost > float(run.cost_budget):
                    run.status = "PAUSED"
                    run.pause_requested = True
                    await self.repo.event(run.id, "RUN_BUDGET_PAUSED", {"budget": "cost"})
                    break
            case_run.status = "RUNNING"
            case_run.started_at = datetime.now(UTC)
            case_run.attempt_count += 1
            if not isinstance(result, dict):
                case_run.status = "SKIPPED"
                case_run.task_outcome = "INDETERMINATE"
                case_run.assertion_results = [
                    {"kind": "replay_fixture", "passed": False, "reason": "missing"}
                ]
            else:
                outcome, metrics, assertions = evaluate_case(case, result)
                case_run.status = "SUCCEEDED" if outcome == "TASK_SUCCESS" else "FAILED"
                case_run.task_outcome = outcome
                case_run.actual_answer = str(result.get("answer") or "")[:12000]
                case_run.result = {
                    key: value
                    for key, value in result.items()
                    if key not in {"prompt", "token", "api_key"}
                }
                case_run.metrics = metrics
                case_run.assertion_results = assertions
                judge = result.get("judge") if isinstance(result.get("judge"), dict) else {}
                case_run.judge_model = str(judge.get("model") or "")[:128] or None
                case_run.judge_prompt_version = str(judge.get("prompt_version") or "")[:64] or None
                case_run.judge_feedback = (
                    judge.get("feedback") if isinstance(judge.get("feedback"), dict) else None
                )
                case_run.judge_confidence = judge.get("confidence")
                if (
                    metrics.get("input_tokens") is not None
                    and metrics.get("output_tokens") is not None
                ):
                    used_tokens += int(metrics["input_tokens"]) + int(metrics["output_tokens"])
                if metrics.get("estimated_cost") is not None:
                    used_cost += float(metrics["estimated_cost"])
            case_run.finished_at = datetime.now(UTC)
            await self.session.commit()
        rows = await self.repo.case_runs(run.id)
        run.completed_cases = sum(x.status in {"SUCCEEDED", "FAILED", "SKIPPED"} for x in rows)
        run.failed_cases = sum(x.status == "FAILED" for x in rows)
        run.metrics = aggregate_metrics(
            [
                {"task_outcome": x.task_outcome, "metrics": x.metrics}
                for x in rows
                if x.status in {"SUCCEEDED", "FAILED", "SKIPPED"}
            ]
        )
        if run.status == "RUNNING":
            run.status = "PARTIAL_FAILED" if run.failed_cases else "SUCCEEDED"
        if run.status in {"SUCCEEDED", "PARTIAL_FAILED", "FAILED", "CANCELLED"}:
            run.finished_at = datetime.now(UTC)
        run.lease_owner = None
        run.lease_until = None
        await self.repo.event(run.id, "RUN_FINISHED", {"status": run.status})
        await self.session.commit()
        return True
