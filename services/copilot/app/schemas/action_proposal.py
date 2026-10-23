from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PurchaseItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_id: int | None = Field(default=None, gt=0)
    quantity: int | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    remark: str | None = Field(default=None, max_length=255)


class PurchaseDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: int | None = Field(default=None, gt=0)
    warehouse_id: int | None = Field(default=None, gt=0)
    expected_arrival_date: date | None = None
    remark: str | None = Field(default=None, max_length=255)
    items: list[PurchaseItemDraft] | None = Field(default=None, min_length=1)


class SalesItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_id: int | None = Field(default=None, gt=0)
    quantity: int | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    remark: str | None = Field(default=None, max_length=255)


class SalesDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int | None = Field(default=None, gt=0)
    warehouse_id: int | None = Field(default=None, gt=0)
    source: str | None = Field(default=None, max_length=16)
    external_order_no: str | None = Field(default=None, max_length=64)
    currency_code: str | None = Field(default=None, max_length=3)
    recipient_name: str | None = Field(default=None, max_length=128)
    recipient_phone: str | None = Field(default=None, max_length=32)
    country_code: str | None = Field(default=None, max_length=2)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=255)
    items: list[SalesItemDraft] | None = Field(default=None, min_length=1)


class TransferItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_id: int | None = Field(default=None, gt=0)
    quantity: int | None = Field(default=None, gt=0)


class TransferDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_warehouse_id: int | None = Field(default=None, gt=0)
    target_warehouse_id: int | None = Field(default=None, gt=0)
    remark: str | None = Field(default=None, max_length=255)
    items: list[TransferItemDraft] | None = Field(default=None, min_length=1)


class PurchaseProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: Literal["PURCHASE_ORDER_CREATE"]
    payload: PurchaseDraft


class SalesProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: Literal["SALES_ORDER_CREATE"]
    payload: SalesDraft


class TransferProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: Literal["INVENTORY_TRANSFER_CREATE"]
    payload: TransferDraft


ActionBody = Annotated[
    PurchaseProposalIn | SalesProposalIn | TransferProposalIn, Field(discriminator="action_type")
]


class ActionProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: int = Field(gt=0)
    source_message_id: int | None = Field(default=None, gt=0)
    idempotency_key: str = Field(
        min_length=8, max_length=128, description="客户端或工具调用生成的稳定幂等键"
    )
    action: ActionBody


class ActionProposalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(gt=0, description="客户端最后读取的版本，用于防止静默覆盖")
    action: ActionBody


class ProposalValidationOut(BaseModel):
    status: str
    revision: int
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    missing_fields: list[str]
    preview_data: dict[str, Any]
    resource_versions: dict[str, Any] = Field(
        description="预检时观察到的 ERP 资源版本，仅用于判断结果是否陈旧"
    )
    validated_at: datetime
    expires_at: datetime


class ActionProposalOut(BaseModel):
    id: int
    conversation_id: int
    source_message_id: int | None
    action_type: str
    schema_version: int
    status: str
    current_revision: int
    payload: dict[str, Any]
    editable_fields: list[str]
    validation: ProposalValidationOut | None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ActionProposalListOut(BaseModel):
    items: list[ActionProposalOut]
    total: int
    page: int
    page_size: int


class ProposalRevisionOut(BaseModel):
    revision: int
    payload: dict[str, Any]
    editor_user_id: int
    created_at: datetime


class ProposalRevisionListOut(BaseModel):
    items: list[ProposalRevisionOut]


class ActionProposalCancel(BaseModel):
    expected_revision: int = Field(gt=0)


class ActionProposalValidate(BaseModel):
    expected_revision: int = Field(gt=0)
