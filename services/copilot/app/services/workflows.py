from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.registry import build_action_registry
from app.ai.types import ModelToolCall
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.erp.client import ErpApiClient
from app.graph.business_workflow import business_workflow_graph
from app.knowledge.client import KnowledgeApiClient
from app.models.action_execution import ActionExecution
from app.models.workflow import WorkflowEvent, WorkflowInstance, WorkflowStep, WorkflowStepAttempt
from app.schemas.action_proposal import ActionProposalCreate
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowDetailOut,
    WorkflowEventOut,
    WorkflowListOut,
    WorkflowMetricsOut,
    WorkflowOut,
    WorkflowStepOut,
)
from app.services.action_proposals import ActionProposalService
from app.services.authorization import AuthorizationService
from app.tasks.queue import enqueue_workflow
from app.tools.executor import ToolExecutor, ToolRuntime
from app.tools.registry import build_tool_registry
from app.workflows.compensation import compensation_registry
from app.workflows.registry import WorkflowRegistry, build_workflow_registry


class ReplenishmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_code: str = Field(min_length=1, max_length=64)
    days: int = Field(default=30, ge=1, le=365)
    warehouse_id: int | None = Field(default=None, gt=0)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=20)
    supplier_id: int | None = Field(default=None, gt=0)
    purchase_warehouse_id: int | None = Field(default=None, gt=0)
    purchase_quantity: int | None = Field(default=None, gt=0)
    unit_price: str | None = Field(default=None, pattern=r"^\d+(\.\d{1,2})?$")


class SalesReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: int = Field(gt=0)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=20)


class WorkflowService:
    """以数据库为权威推进确定性工作流，外部调用期间不持有数据库事务。"""

    def __init__(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        access_token: str,
        request_id: str,
        erp: ErpApiClient,
        knowledge: KnowledgeApiClient,
        audiences: tuple[str, ...] = (),
    ) -> None:
        self.session = session
        self.context = context
        self.access_token = access_token
        self.request_id = request_id
        self.erp = erp
        self.knowledge = knowledge
        self.registry: WorkflowRegistry = build_workflow_registry()
        self.auth = AuthorizationService()
        self.executor = ToolExecutor(build_tool_registry(), erp, knowledge)
        self.audiences = frozenset(audiences)

    def _validate_input(self, workflow_type: str, value: dict[str, Any]) -> dict[str, Any]:
        try:
            model = (
                ReplenishmentInput
                if workflow_type == "INVENTORY_REPLENISHMENT_WORKFLOW"
                else SalesReviewInput
            )
            return model.model_validate(value).model_dump(mode="json")
        except ValidationError as exc:
            raise AppError(
                "工作流输入无效",
                code=42290,
                status_code=422,
                data={"errors": exc.errors(include_url=False)},
            ) from exc

    async def _owned(self, workflow_id: int, *, lock: bool = False) -> WorkflowInstance:
        statement = select(WorkflowInstance).where(
            WorkflowInstance.id == workflow_id,
            WorkflowInstance.tenant_id == self.context.tenant_id,
            WorkflowInstance.user_id == self.context.user_id,
        )
        if lock:
            statement = statement.with_for_update()
        row = await self.session.scalar(statement)
        if row is None:
            raise AppError("工作流不存在", code=40490, status_code=404)
        return row

    async def create(self, data: WorkflowCreate) -> WorkflowOut:
        spec = self.registry.get(data.workflow_type)
        self.auth.require_all(self.context, spec.permissions)
        normalized = self._validate_input(data.workflow_type, data.input)
        existing = await self.session.scalar(
            select(WorkflowInstance).where(
                WorkflowInstance.tenant_id == self.context.tenant_id,
                WorkflowInstance.user_id == self.context.user_id,
                WorkflowInstance.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            if (
                existing.workflow_type != data.workflow_type
                or existing.input_snapshot != normalized
            ):
                raise AppError("幂等键已用于不同工作流", code=40995, status_code=409)
            return self._out(existing)
        row = WorkflowInstance(
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            conversation_id=data.conversation_id,
            workflow_type=spec.workflow_type,
            schema_version=spec.schema_version,
            status="CREATED",
            current_step=spec.steps[0].key,
            graph_thread_id="pending",
            idempotency_key=data.idempotency_key,
            input_snapshot=normalized,
            result_summary={},
        )
        self.session.add(row)
        await self.session.flush()
        row.graph_thread_id = f"business-workflow:{row.id}"
        for step in spec.steps:
            self.session.add(
                WorkflowStep(
                    tenant_id=row.tenant_id,
                    workflow_id=row.id,
                    step_key=step.key,
                    step_type=step.step_type,
                    status="PENDING",
                    safe_result_summary={},
                )
            )
        self._event(row, "WORKFLOW_CREATED", {"workflow_type": row.workflow_type})
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("工作流启动冲突", code=40995, status_code=409) from exc
        if settings.action_graph_enabled:
            await business_workflow_graph.begin(
                {
                    "workflow_id": row.id,
                    "tenant_id": row.tenant_id,
                    "user_id": row.user_id,
                    "workflow_type": row.workflow_type,
                    "phase": "created",
                }
            )
        return await self.advance(row.id, {})

    async def advance(self, workflow_id: int, additional_input: dict[str, Any]) -> WorkflowOut:
        row = await self._owned(workflow_id, lock=True)
        if row.status in {"SUCCEEDED", "CANCELLED", "EXPIRED", "NEEDS_MANUAL_INTERVENTION"}:
            return self._out(row)
        spec = self.registry.get(row.workflow_type)
        self.auth.require_all(self.context, spec.permissions)
        merged = dict(row.input_snapshot) | additional_input
        row.input_snapshot = self._validate_input(row.workflow_type, merged)
        row.status = "RUNNING"
        row.run_attempts += 1
        self._event(row, "WORKFLOW_RESUMED", {"attempt": row.run_attempts})
        await self.session.commit()
        try:
            if row.workflow_type == "INVENTORY_REPLENISHMENT_WORKFLOW":
                await self._advance_replenishment(row)
            else:
                await self._advance_sales_review(row)
        except AppError as exc:
            await self.session.rollback()
            row = await self._owned(workflow_id, lock=True)
            row.status = (
                "PAUSED"
                if exc.status_code >= 500 and row.run_attempts < settings.workflow_max_attempts
                else "FAILED"
            )
            self._event(
                row, "WORKFLOW_STEP_FAILED", {"code": exc.code, "retryable": row.status == "PAUSED"}
            )
            await self.session.commit()
            if row.status == "PAUSED":
                await enqueue_workflow(row.tenant_id, row.id)
            raise
        return self._out(row)

    def _runtime(self) -> ToolRuntime:
        return ToolRuntime(
            tenant=self.context,
            access_token=self.access_token,
            erp_audience_authorized=settings.erp_jwt_audience in self.audiences,
            knowledge_audience_authorized=settings.knowledge_jwt_audience in self.audiences,
            request_id=self.request_id,
        )

    @staticmethod
    def _tool_json(content: str) -> Any:
        start = content.find("\n") + 1
        end = content.rfind("\n</")
        if start <= 0 or end <= start:
            start = content.find(">") + 1
            end = content.rfind("</")
        return json.loads(content[start:end])

    async def _run_tool(self, name: str, arguments: dict[str, Any], runtime: ToolRuntime) -> Any:
        result = await self.executor.execute(
            ModelToolCall(
                id=f"workflow-{name}",
                name=name,
                arguments=json.dumps(arguments, ensure_ascii=False),
            ),
            runtime,
        )
        return self._tool_json(result.content)

    async def _step(self, row: WorkflowInstance, key: str, work) -> Any:
        step = await self.session.scalar(
            select(WorkflowStep)
            .where(
                WorkflowStep.tenant_id == row.tenant_id,
                WorkflowStep.workflow_id == row.id,
                WorkflowStep.step_key == key,
            )
            .with_for_update()
        )
        if step is None:
            raise AppError("工作流步骤定义缺失", code=50090, status_code=500)
        if step.status == "SUCCEEDED":
            return step.safe_result_summary
        now = datetime.now(UTC)
        step.status = "RUNNING"
        step.attempt_count += 1
        step.started_at = now
        attempt = WorkflowStepAttempt(
            tenant_id=row.tenant_id,
            step_id=step.id,
            attempt_no=step.attempt_count,
            status="RUNNING",
            started_at=now,
        )
        self.session.add(attempt)
        row.current_step = key
        await self.session.commit()
        try:
            result = await work()
        except Exception as exc:
            step.status = "FAILED"
            step.error_code = getattr(exc, "code", type(exc).__name__)
            step.completed_at = datetime.now(UTC)
            attempt.status = "FAILED"
            attempt.error_code = step.error_code
            attempt.completed_at = step.completed_at
            await self.session.commit()
            raise
        step.status = "SUCCEEDED"
        step.safe_result_summary = result
        step.completed_at = datetime.now(UTC)
        attempt.status = "SUCCEEDED"
        attempt.completed_at = step.completed_at
        self._event(row, "WORKFLOW_STEP_SUCCEEDED", {"step_key": key})
        await self.session.commit()
        return result

    async def _mark_step(
        self, row: WorkflowInstance, key: str, status: str, summary: dict[str, Any]
    ) -> None:
        step = await self.session.scalar(
            select(WorkflowStep)
            .where(
                WorkflowStep.tenant_id == row.tenant_id,
                WorkflowStep.workflow_id == row.id,
                WorkflowStep.step_key == key,
            )
            .with_for_update()
        )
        if step is None:
            raise AppError("工作流步骤定义缺失", code=50090, status_code=500)
        if step.status == "SUCCEEDED" and status != "SUCCEEDED":
            return
        step.status = status
        step.safe_result_summary = summary
        if status in {"SUCCEEDED", "SKIPPED", "CANCELLED"}:
            step.completed_at = datetime.now(UTC)
        row.current_step = key
        await self.session.commit()

    async def _advance_replenishment(self, row: WorkflowInstance) -> None:
        values = row.input_snapshot
        runtime = self._runtime()
        end = date.today()
        start = end - timedelta(days=int(values["days"]) - 1)
        await self._mark_step(
            row,
            "validate_input",
            "SUCCEEDED",
            {"sku_code": values["sku_code"], "days": values["days"]},
        )
        analysis = await self._step(
            row,
            "inventory_analysis",
            lambda: self._run_tool(
                "analyze_inventory_coverage",
                {
                    "sku_code": values["sku_code"],
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    **(
                        {"warehouse_id": values["warehouse_id"]}
                        if values.get("warehouse_id")
                        else {}
                    ),
                },
                runtime,
            ),
        )
        row.result_summary = {
            "analysis": analysis,
            "warning": "系统没有可信安全库存、交付周期或在途规则，不会自动计算采购数量。",
        }
        if values.get("knowledge_base_ids"):
            rules = await self._step(
                row,
                "knowledge_rules",
                lambda: self._run_tool(
                    "search_knowledge",
                    {
                        "query": f"SKU {values['sku_code']} 补货、采购审批和库存规则",
                        "knowledge_base_ids": values["knowledge_base_ids"],
                        "top_k": 5,
                    },
                    runtime,
                ),
            )
            row.result_summary = {
                **row.result_summary,
                "knowledge": {
                    "matches": len(rules.get("items", [])),
                    "citations": [
                        item.get("citation_id")
                        for item in rules.get("items", [])
                        if item.get("citation_id")
                    ],
                },
            }
        else:
            await self._mark_step(row, "knowledge_rules", "SKIPPED", {"reason": "未选择知识库"})
        required = [
            name
            for name in ("supplier_id", "purchase_warehouse_id", "purchase_quantity")
            if not values.get(name)
        ]
        if required:
            await self._mark_step(row, "purchase_input", "WAITING", {"required_fields": required})
            row.status = "WAITING_INPUT"
            row.current_step = "purchase_input"
            row.result_summary = {**row.result_summary, "required_fields": required}
            self._event(row, "WORKFLOW_INPUT_REQUIRED", {"fields": required})
            await self.session.commit()
            return
        await self._mark_step(row, "purchase_input", "SUCCEEDED", {"provided": True})
        self.auth.require_all(self.context, (PermissionCode.PURCHASE_CREATE,))
        if row.conversation_id is None:
            raise AppError("生成采购草稿需要关联会话", code=42291, status_code=422)

        async def make_proposal() -> dict[str, Any]:
            service = ActionProposalService(
                self.session,
                self.context,
                erp_client=self.erp,
                access_token=self.access_token,
                request_id=self.request_id,
                registry=build_action_registry(),
            )
            item: dict[str, Any] = {
                "sku_id": analysis.get("sku_id"),
                "quantity": values["purchase_quantity"],
            }
            if values.get("unit_price") is not None:
                item["unit_price"] = values["unit_price"]
            created = await service.create(
                ActionProposalCreate.model_validate(
                    {
                        "conversation_id": row.conversation_id,
                        "idempotency_key": f"workflow:{row.id}:purchase:v1",
                        "action": {
                            "action_type": "PURCHASE_ORDER_CREATE",
                            "payload": {
                                "supplier_id": values["supplier_id"],
                                "warehouse_id": values["purchase_warehouse_id"],
                                "items": [item],
                                "remark": f"Copilot Workflow #{row.id}",
                            },
                        },
                    }
                )
            )
            validated = await service.validate(created.id, created.current_revision)
            row.proposal_id = validated.id
            return {
                "proposal_id": validated.id,
                "revision": validated.current_revision,
                "status": validated.status,
            }

        proposal = await self._step(row, "proposal", make_proposal)
        row.proposal_id = int(proposal["proposal_id"])
        if row.execution_id is None:
            await self._mark_step(row, "execution", "WAITING", {"proposal_id": row.proposal_id})
            row.status = "WAITING_CONFIRMATION"
            row.current_step = "execution"
            row.result_summary = {**row.result_summary, "proposal": proposal}
            self._event(row, "WORKFLOW_CONFIRMATION_REQUIRED", {"proposal_id": row.proposal_id})
            await self.session.commit()
            return
        execution = await self.session.scalar(
            select(ActionExecution).where(
                ActionExecution.id == row.execution_id,
                ActionExecution.tenant_id == row.tenant_id,
                ActionExecution.user_id == row.user_id,
                ActionExecution.proposal_id == row.proposal_id,
            )
        )
        if execution is None:
            raise AppError("关联执行不存在", code=40491, status_code=404)
        if execution.status == "SUCCEEDED":
            await self._mark_step(row, "execution", "SUCCEEDED", {"execution_id": execution.id})
            await self._mark_step(row, "finalize", "SUCCEEDED", {"execution_id": execution.id})
            row.status = "SUCCEEDED"
            row.current_step = "finalize"
            row.completed_at = datetime.now(UTC)
            erp_summary = {
                "resource_type": execution.erp_resource_type,
                "resource_id": execution.erp_resource_id,
                "resource_no": execution.erp_resource_no,
            }
            row.result_summary = {**row.result_summary, "erp": erp_summary}
            self._event(row, "WORKFLOW_SUCCEEDED", erp_summary)
        elif execution.status in {"UNKNOWN", "RECONCILING", "EXECUTING"}:
            await self._mark_step(row, "execution", "UNKNOWN", {"execution_id": execution.id})
            row.status = "RECONCILING"
        elif execution.status == "WAITING_APPROVAL":
            await self._mark_step(row, "execution", "WAITING", {"execution_id": execution.id})
            row.status = "WAITING_APPROVAL"
        elif execution.status in {"FAILED", "REJECTED", "CANCELLED", "EXPIRED"}:
            row.status = "NEEDS_MANUAL_INTERVENTION"
            row.result_summary = {
                **row.result_summary,
                "recovery": compensation_registry.for_step("V6_EXECUTION").reason,
            }
        else:
            row.status = "WAITING_CONFIRMATION"
        await self.session.commit()
        if row.status == "RECONCILING":
            await enqueue_workflow(row.tenant_id, row.id)

    async def _advance_sales_review(self, row: WorkflowInstance) -> None:
        values = row.input_snapshot
        runtime = self._runtime()
        await self._mark_step(row, "validate_input", "SUCCEEDED", {"order_id": values["order_id"]})
        order = await self._step(
            row,
            "order_lookup",
            lambda: self._run_tool("get_sales_order", {"order_id": values["order_id"]}, runtime),
        )
        rules: dict[str, Any] = {}
        if values.get("knowledge_base_ids"):
            rules = await self._step(
                row,
                "knowledge_rules",
                lambda: self._run_tool(
                    "search_knowledge",
                    {
                        "query": "销售订单出库、库存、审核和拣货规则",
                        "knowledge_base_ids": values["knowledge_base_ids"],
                        "top_k": 5,
                    },
                    runtime,
                ),
            )
        else:
            await self._mark_step(row, "knowledge_rules", "SKIPPED", {"reason": "未选择知识库"})
        status = str(order.get("status") or "") if isinstance(order, dict) else ""
        conclusion = (
            "NOT_ELIGIBLE"
            if status not in {"WAITING_OUTBOUND", "CONFIRMED"}
            else "UNABLE_TO_DETERMINE"
        )
        reason = (
            "订单状态不在待出库范围"
            if conclusion == "NOT_ELIGIBLE"
            else "缺少完整拣货记录、仓库作业状态或实时操作日志，不能断言可出库"
        )
        row.result_summary = {
            "conclusion": conclusion,
            "reason": reason,
            "order_id": values["order_id"],
            "order_status": status,
            "knowledge_matches": len(rules.get("items", [])) if isinstance(rules, dict) else 0,
        }
        await self._mark_step(
            row, "risk_analysis", "SUCCEEDED", {"conclusion": conclusion, "reason": reason}
        )
        await self._mark_step(row, "finalize", "SUCCEEDED", {"conclusion": conclusion})
        row.status = "SUCCEEDED"
        row.current_step = "finalize"
        row.completed_at = datetime.now(UTC)
        self._event(row, "WORKFLOW_SUCCEEDED", {"conclusion": conclusion})
        await self.session.commit()

    async def attach_execution(self, workflow_id: int, execution_id: int) -> WorkflowOut:
        row = await self._owned(workflow_id, lock=True)
        if row.status not in {"WAITING_CONFIRMATION", "WAITING_APPROVAL", "RECONCILING"}:
            raise AppError("当前状态不能关联执行", code=40996, status_code=409)
        row.execution_id = execution_id
        await self.session.commit()
        if settings.action_graph_enabled:
            await business_workflow_graph.resume(
                row.id,
                {
                    "workflow_id": row.id,
                    "tenant_id": row.tenant_id,
                    "user_id": row.user_id,
                    "execution_id": execution_id,
                },
            )
        return await self.advance(row.id, {})

    async def cancel(self, workflow_id: int) -> WorkflowOut:
        row = await self._owned(workflow_id, lock=True)
        if row.status in {"SUCCEEDED", "CANCELLED", "EXPIRED"}:
            return self._out(row)
        if row.execution_id is not None:
            execution = await self.session.scalar(
                select(ActionExecution).where(
                    ActionExecution.id == row.execution_id,
                    ActionExecution.tenant_id == row.tenant_id,
                )
            )
            if execution is not None and execution.status == "SUCCEEDED":
                row.status = "NEEDS_MANUAL_INTERVENTION"
                row.result_summary = {
                    **row.result_summary,
                    "recovery": "ERP 单据已创建，停止后续调度但不会自动删除业务单据",
                }
            else:
                row.status = "CANCELLED"
        else:
            row.status = "CANCELLED"
        row.completed_at = datetime.now(UTC)
        self._event(row, "WORKFLOW_CANCELLED", {"erp_rollback": False})
        await self.session.commit()
        return self._out(row)

    async def list(self, page: int, page_size: int) -> WorkflowListOut:
        filters = (
            WorkflowInstance.tenant_id == self.context.tenant_id,
            WorkflowInstance.user_id == self.context.user_id,
        )
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(WorkflowInstance).where(*filters)
            )
            or 0
        )
        rows = (
            await self.session.scalars(
                select(WorkflowInstance)
                .where(*filters)
                .order_by(WorkflowInstance.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return WorkflowListOut(
            items=[self._out(row) for row in rows], total=total, page=page, page_size=page_size
        )

    async def metrics(self) -> WorkflowMetricsOut:
        """返回当前租户和用户范围内的基础流程指标，避免跨租户聚合泄露。"""
        filters = (
            WorkflowInstance.tenant_id == self.context.tenant_id,
            WorkflowInstance.user_id == self.context.user_id,
        )
        rows = (await self.session.scalars(select(WorkflowInstance).where(*filters))).all()
        durations = [
            (row.completed_at - row.created_at).total_seconds()
            for row in rows
            if row.completed_at is not None
        ]
        workflow_ids = [row.id for row in rows]
        steps = (
            (
                await self.session.scalars(
                    select(WorkflowStep).where(
                        WorkflowStep.tenant_id == self.context.tenant_id,
                        WorkflowStep.workflow_id.in_(workflow_ids),
                    )
                )
            ).all()
            if workflow_ids
            else []
        )
        step_durations: dict[str, list[float]] = {}
        for step in steps:
            if step.started_at is not None and step.completed_at is not None:
                step_durations.setdefault(step.step_key, []).append(
                    (step.completed_at - step.started_at).total_seconds()
                )
        events = (
            (
                await self.session.scalars(
                    select(WorkflowEvent).where(
                        WorkflowEvent.tenant_id == self.context.tenant_id,
                        WorkflowEvent.workflow_id.in_(workflow_ids),
                        WorkflowEvent.event_type.in_(
                            ("WORKFLOW_RECONCILED", "WORKFLOW_RECONCILIATION_EXHAUSTED")
                        ),
                    )
                )
            ).all()
            if workflow_ids
            else []
        )
        reconciliation_total = len(events)
        reconciliation_succeeded = sum(
            event.event_type == "WORKFLOW_RECONCILED" for event in events
        )
        succeeded = sum(row.status == "SUCCEEDED" for row in rows)
        failed = sum(row.status == "FAILED" for row in rows)
        return WorkflowMetricsOut(
            total=len(rows),
            succeeded=succeeded,
            failed=failed,
            success_rate=(succeeded / len(rows) if rows else 0.0),
            failure_rate=(failed / len(rows) if rows else 0.0),
            reconciling=sum(row.status == "RECONCILING" for row in rows),
            manual_intervention=sum(row.status == "NEEDS_MANUAL_INTERVENTION" for row in rows),
            average_duration_seconds=(sum(durations) / len(durations) if durations else None),
            average_step_duration_seconds={
                key: sum(values) / len(values) for key, values in step_durations.items()
            },
            total_step_retries=sum(max(0, step.attempt_count - 1) for step in steps),
            reconciliation_success_rate=(
                reconciliation_succeeded / reconciliation_total
                if reconciliation_total
                else None
            ),
        )

    async def detail(self, workflow_id: int) -> WorkflowDetailOut:
        row = await self._owned(workflow_id)
        steps = (
            await self.session.scalars(
                select(WorkflowStep)
                .where(WorkflowStep.tenant_id == row.tenant_id, WorkflowStep.workflow_id == row.id)
                .order_by(WorkflowStep.id)
            )
        ).all()
        events = (
            await self.session.scalars(
                select(WorkflowEvent)
                .where(
                    WorkflowEvent.tenant_id == row.tenant_id, WorkflowEvent.workflow_id == row.id
                )
                .order_by(WorkflowEvent.id)
            )
        ).all()
        return WorkflowDetailOut(
            **self._out(row).model_dump(),
            steps=[WorkflowStepOut.model_validate(item, from_attributes=True) for item in steps],
            events=[WorkflowEventOut.model_validate(item, from_attributes=True) for item in events],
        )

    def _event(self, row: WorkflowInstance, event_type: str, data: dict[str, Any]) -> None:
        self.session.add(
            WorkflowEvent(
                tenant_id=row.tenant_id, workflow_id=row.id, event_type=event_type, event_data=data
            )
        )

    @staticmethod
    def _out(row: WorkflowInstance) -> WorkflowOut:
        return WorkflowOut.model_validate(row, from_attributes=True)
