from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfirmationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(gt=0, description="用户实际查看并确认的草稿版本")
    client_request_id: str = Field(
        min_length=8, max_length=128, description="防止前端重复点击的稳定请求标识"
    )


class ConfirmationTicketOut(BaseModel):
    execution_id: int
    confirmation_nonce: str = Field(description="一次性确认票据，仅本次响应返回明文")
    expires_at: datetime
    requires_approval: bool
    risk_level: str
    proposal_revision: int
    payload_hash: str


class ExecutionConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(gt=0)
    confirmation_nonce: str = Field(
        min_length=32, max_length=256, description="创建确认请求时签发的一次性票据"
    )


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_reason: str | None = Field(default=None, max_length=500)


class ExecutionResume(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(gt=0)


class ActionApprovalOut(BaseModel):
    id: int
    proposal_id: int
    proposal_revision: int
    execution_id: int
    applicant_user_id: int
    approver_user_id: int | None
    status: str
    decision: str | None
    decision_reason: str | None
    requested_at: datetime
    decided_at: datetime | None
    expires_at: datetime


class ActionExecutionOut(BaseModel):
    id: int
    proposal_id: int
    proposal_revision: int
    action_type: str
    status: str
    risk_level: str
    approval_id: int | None
    erp_resource_type: str | None
    erp_resource_id: int | None
    erp_resource_no: str | None
    error_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActionExecutionListOut(BaseModel):
    items: list[ActionExecutionOut]
    total: int
    page: int
    page_size: int


class ActionApprovalListOut(BaseModel):
    items: list[ActionApprovalOut]
    total: int
    page: int
    page_size: int


class ActionAuditEventOut(BaseModel):
    id: int
    actor_user_id: int | None
    event_type: str
    outcome: str
    details: dict[str, Any]
    created_at: datetime


class ActionAuditListOut(BaseModel):
    items: list[ActionAuditEventOut]
