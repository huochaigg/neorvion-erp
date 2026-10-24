from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

WorkflowType = Literal["INVENTORY_REPLENISHMENT_WORKFLOW", "SALES_ORDER_REVIEW_WORKFLOW"]


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_type: WorkflowType
    conversation_id: int | None = Field(default=None, gt=0)
    idempotency_key: str = Field(
        min_length=8, max_length=128, description="同一用户启动工作流的稳定幂等键"
    )
    input: dict[str, Any] = Field(description="由具体 Workflow Schema 再次严格校验的输入快照")


class WorkflowResume(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict[str, Any] = Field(
        default_factory=dict, description="补充业务字段或关联 V6 execution_id"
    )


class WorkflowStepOut(BaseModel):
    id: int
    step_key: str
    step_type: str
    status: str
    attempt_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    safe_result_summary: dict[str, Any]


class WorkflowEventOut(BaseModel):
    id: int
    event_type: str
    event_data: dict[str, Any]
    created_at: datetime


class WorkflowOut(BaseModel):
    id: int
    workflow_type: str
    schema_version: int
    status: str
    current_step: str
    input_snapshot: dict[str, Any]
    result_summary: dict[str, Any]
    proposal_id: int | None
    execution_id: int | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class WorkflowDetailOut(WorkflowOut):
    steps: list[WorkflowStepOut]
    events: list[WorkflowEventOut]


class WorkflowListOut(BaseModel):
    items: list[WorkflowOut]
    total: int
    page: int
    page_size: int


class WorkflowMetricsOut(BaseModel):
    total: int
    succeeded: int
    failed: int
    success_rate: float
    failure_rate: float
    reconciling: int
    manual_intervention: int
    average_duration_seconds: float | None
    average_step_duration_seconds: dict[str, float]
    total_step_retries: int
    reconciliation_success_rate: float | None
