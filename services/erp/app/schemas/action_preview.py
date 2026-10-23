from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActionPreviewIssue(BaseModel):
    code: str
    message: str
    field: str | None = None


class ActionPreviewOut(BaseModel):
    valid: bool
    blocking_errors: list[ActionPreviewIssue] = Field(default_factory=list)
    warnings: list[ActionPreviewIssue] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    normalized_payload: dict[str, Any]
    preview_summary: dict[str, Any]
    resource_versions: dict[str, Any] = Field(
        default_factory=dict,
        description="预检时观察到的 ERP 资源版本；后续正式执行前仍须重新校验",
    )
    validated_at: datetime
    expires_at: datetime
