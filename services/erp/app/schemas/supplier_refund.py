from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class SupplierRefundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="本次供应商退款金额。不填则等于批准剩余可退金额",
    )
    external_reference_no: str | None = Field(
        default=None,
        max_length=64,
        description="外部银行或供应商付款流水号，本版仅人工记录",
    )

    @field_validator("external_reference_no")
    @classmethod
    def clean_external(cls, value: str | None) -> str | None:
        return _blank(value)


class SupplierRefundConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_reference_no: str | None = Field(
        default=None,
        max_length=64,
        description="外部银行或供应商付款流水号",
    )
    received_at: datetime | None = Field(default=None, description="供应商退款到账时间")

    @field_validator("external_reference_no")
    @classmethod
    def clean_external(cls, value: str | None) -> str | None:
        return _blank(value)


class SupplierRefundFail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_reason: str = Field(min_length=1, max_length=255, description="失败原因")

    @field_validator("failure_reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("失败原因不能为空")
        return text


class SupplierRefundRecordOut(BaseModel):
    id: int
    refund_no: str
    purchase_return_id: int
    purchase_return_no: str
    purchase_order_id: int
    purchase_order_no: str
    supplier_id: int
    supplier_name: str
    amount: float = Field(description="本次供应商退款金额，不能超过批准剩余可退金额")
    status: str
    external_reference_no: str | None
    failure_reason: str | None
    received_at: datetime | None
    created_by: int
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class SupplierRefundListOut(BaseModel):
    items: list[SupplierRefundRecordOut]
    total: int
    page: int
    page_size: int
