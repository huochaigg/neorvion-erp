from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class RefundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="本次退款金额。不填则等于售后剩余可退金额",
    )
    external_reference_no: str | None = Field(
        default=None,
        max_length=64,
        description="外部渠道退款流水号，本版仅人工记录",
    )
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("external_reference_no", "remark")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _blank(value)


class RefundConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_reference_no: str | None = Field(
        default=None,
        max_length=64,
        description="外部渠道退款流水号",
    )
    refunded_at: datetime | None = Field(default=None, description="外部退款完成时间")
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("external_reference_no", "remark")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return _blank(value)


class RefundFail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_reason: str = Field(min_length=1, max_length=255, description="退款失败原因")

    @field_validator("failure_reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("失败原因不能为空")
        return text


class RefundRecordOut(BaseModel):
    id: int
    refund_no: str
    after_sale_order_id: int
    after_sale_no: str
    sales_order_id: int
    sales_order_no: str
    customer_id: int
    customer_name: str
    amount: float
    status: str
    external_reference_no: str | None
    failure_reason: str | None
    refunded_at: datetime | None
    created_by: int
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class RefundListOut(BaseModel):
    items: list[RefundRecordOut]
    total: int
    page: int
    page_size: int
