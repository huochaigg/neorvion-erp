from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DetectorType = Literal[
    "LOW_STOCK_RISK", "OVERDUE_SHIPMENT", "PURCHASE_ARRIVAL_DELAY", "INVENTORY_COVERAGE_RISK"
]


class InsightRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    detector_type: DetectorType
    config: dict[str, Any] = Field(description="由固定 Detector Schema 校验，禁止表达式和动态 SQL")
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    interval_minutes: int = Field(default=60, ge=15, le=43_200)
    enabled: bool = False
    severity_config: dict[str, Any] = Field(default_factory=dict)
    cooldown_seconds: int = Field(default=3600, ge=60, le=2_592_000)
    max_alerts_per_run: int = Field(default=100, ge=1, le=500)


class InsightRulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    config: dict[str, Any] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    interval_minutes: int | None = Field(default=None, ge=15, le=43_200)
    enabled: bool | None = None
    severity_config: dict[str, Any] | None = None
    cooldown_seconds: int | None = Field(default=None, ge=60, le=2_592_000)
    max_alerts_per_run: int | None = Field(default=None, ge=1, le=500)


class InsightRuleOut(InsightRuleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    detector_version: str
    next_run_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class InsightRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_id: int
    schedule_key: str
    detector_version: str
    status: str
    detected_count: int
    duplicate_count: int
    error_code: int | None
    safe_error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class BusinessInsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_id: int
    detection_run_id: int
    detector_type: str
    resource_type: str
    resource_id: str
    severity: str
    status: str
    detected_at: datetime
    last_seen_at: datetime
    snoozed_until: datetime | None
    resolved_at: datetime | None
    evidence_summary: dict[str, Any]
    analysis_status: str
    ai_summary: str | None
    recommendations: list[dict[str, Any]]


class InsightAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snoozed_until: datetime | None = Field(
        default=None, description="仅 snooze 操作需要，必须是未来时间"
    )


class InsightEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: str
    actor_user_id: int | None
    safe_summary: dict[str, Any]
    created_at: datetime


class InsightNotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    insight_id: int
    title: str
    safe_body: str
    severity: str
    read_at: datetime | None
    created_at: datetime
