from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OperationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int | None = None
    operator_user_id: int | None = Field(None, description="执行操作的用户 id")
    action: str = Field(..., description="稳定动作编码，例如 CONFIRM，不是自然语言")
    module: str
    resource_type: str | None = None
    resource_id: int | None = None
    resource_name: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    request_id: str | None = Field(None, description="HTTP 请求标识，用于关联后端日志")
    result: str = Field(..., description="SUCCESS 或 FAILED")
    error_code: str | None = None
    description: str | None = None
    metadata: dict[str, Any] | None = None
    occurred_at: datetime


class OperationLogListOut(BaseModel):
    items: list[OperationLogOut]
    total: int
    page: int
    page_size: int
