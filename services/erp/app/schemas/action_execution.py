from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActionExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_key: str = Field(
        min_length=16, max_length=128, description="Copilot 生成的最终写入幂等键"
    )
    action_type: Literal["PURCHASE_ORDER_CREATE", "SALES_ORDER_CREATE", "INVENTORY_TRANSFER_CREATE"]
    proposal_revision: int = Field(gt=0, description="确认并获批的不可变草稿版本")
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$", description="规范化执行参数 SHA-256")
    payload: dict[str, Any]

    @model_validator(mode="after")
    def action_matches_route_payload(self) -> ActionExecutionRequest:
        if not self.payload:
            raise ValueError("执行参数不能为空")
        return self


class ActionExecutionReceiptOut(BaseModel):
    execution_key: str
    action_type: str
    payload_hash: str
    status: str
    resource_type: str | None
    resource_id: int | None
    resource_no: str | None
