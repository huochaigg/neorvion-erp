from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class PurchaseReturnItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_order_item_id: int = Field(gt=0, description="原采购订单明细 id")
    purchase_receipt_item_id: int | None = Field(
        default=None,
        gt=0,
        description="可选关联某次收货明细，可退数量仍按采购明细累计已收计算",
    )
    requested_return_quantity: int = Field(
        gt=0,
        description="本次申请退给供应商的数量，不能超过当前可退数量",
    )
    requested_refund_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="本明细申请供应商退回的金额",
    )
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return _blank(value)


class PurchaseReturnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purchase_order_id: int = Field(gt=0, description="必须关联原采购单")
    warehouse_id: int | None = Field(
        default=None,
        gt=0,
        description="退货仓库。不填则使用原采购单仓库",
    )
    settlement_type: str = Field(
        min_length=1,
        max_length=16,
        description="REFUND：退货后等待供应商退款；NO_REFUND：只退货不跟踪退款",
    )
    reason: str = Field(min_length=1, max_length=255, description="退货原因")
    description: str | None = Field(default=None, max_length=512)
    items: list[PurchaseReturnItemIn] = Field(min_length=1)

    @field_validator("settlement_type")
    @classmethod
    def clean_type(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("退货原因不能为空")
        return text

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return _blank(value)

    @model_validator(mode="after")
    def unique_items(self) -> "PurchaseReturnCreate":
        ids = [row.purchase_order_item_id for row in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一采购退货单中同一个采购明细只能出现一行")
        return self


class PurchaseReturnUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_id: int | None = Field(default=None, gt=0)
    settlement_type: str | None = Field(default=None, max_length=16)
    reason: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=512)
    items: list[PurchaseReturnItemIn] | None = None

    @field_validator("settlement_type")
    @classmethod
    def clean_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return _blank(value)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return _blank(value)


class PurchaseReturnApproveItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    approved_return_quantity: int = Field(
        ge=0,
        description="审核最终允许退给供应商的数量，不能超过申请退货数量",
    )
    approved_refund_amount: Decimal = Field(
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="审核最终同意的本明细退款金额，不能超过申请金额",
    )


class PurchaseReturnApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PurchaseReturnApproveItemIn] = Field(default_factory=list)


class PurchaseReturnReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=255, description="拒绝原因")

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("拒绝原因不能为空")
        return text


class PurchaseReturnItemOut(BaseModel):
    id: int
    purchase_order_item_id: int
    purchase_receipt_item_id: int | None
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict[str, Any]
    original_ordered_quantity: int = Field(description="原采购明细的计划采购数量，不是可退上限")
    original_received_quantity: int = Field(
        description="原采购明细累计实际收货入库数量快照，不等于采购计划数量",
    )
    requested_return_quantity: int = Field(description="本次申请退给供应商的数量")
    approved_return_quantity: int | None = Field(
        description="审核最终允许退给供应商的数量，不能超过申请退货数量",
    )
    returned_quantity: int = Field(description="已经真正完成退货出库的累计数量")
    remaining_return_quantity: int = Field(description="批准数量减去已出库数量，待退剩余")
    inventory_quantity: int = 0
    inventory_reserved: int = 0
    inventory_available: int = Field(
        default=0,
        description="当前退货仓可用库存；确认出库时单次不能超过它",
    )
    requested_refund_amount: float | None
    approved_refund_amount: float | None
    unit_price: float | None
    reason: str | None


class PurchaseReturnOutboundItemOut(BaseModel):
    id: int
    purchase_return_item_id: int
    sku_id: int
    sku_code: str
    quantity: int = Field(description="本次实际退货出库数量，不是累计已退")


class PurchaseReturnOutboundBriefOut(BaseModel):
    id: int
    outbound_no: str
    warehouse_id: int
    status: str
    remark: str | None
    confirmed_at: datetime | None
    confirmed_by: int | None
    created_at: datetime
    items: list[PurchaseReturnOutboundItemOut] = Field(default_factory=list)


class SupplierRefundBriefOut(BaseModel):
    id: int
    refund_no: str
    amount: float
    status: str
    external_reference_no: str | None
    failure_reason: str | None
    received_at: datetime | None
    created_at: datetime


class PurchaseReturnOut(BaseModel):
    id: int
    purchase_return_no: str
    purchase_order_id: int
    purchase_order_no: str
    supplier_id: int
    supplier_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    settlement_type: str = Field(
        description="REFUND：退货后等待供应商退款；NO_REFUND：只退货不跟踪退款",
    )
    reason: str
    description: str | None
    requested_refund_amount: float
    approved_refund_amount: float | None
    refund_status: str
    sku_count: int
    requested_return_quantity: int
    approved_return_quantity: int | None
    returned_quantity: int
    created_by: int
    created_by_name: str | None
    approved_by: int | None
    approved_by_name: str | None
    approved_at: datetime | None
    rejected_by: int | None
    rejected_at: datetime | None
    reject_reason: str | None
    outbound_at: datetime | None
    outbound_by: int | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancelled_by: int | None
    created_at: datetime
    updated_at: datetime
    items: list[PurchaseReturnItemOut] = Field(default_factory=list)
    outbounds: list[PurchaseReturnOutboundBriefOut] = Field(default_factory=list)
    refunds: list[SupplierRefundBriefOut] = Field(default_factory=list)


class PurchaseReturnListItem(BaseModel):
    id: int
    purchase_return_no: str
    purchase_order_id: int
    purchase_order_no: str
    supplier_id: int
    supplier_name: str
    warehouse_id: int
    warehouse_name: str
    sku_count: int
    requested_return_quantity: int
    approved_return_quantity: int | None
    returned_quantity: int
    requested_refund_amount: float
    approved_refund_amount: float | None
    status: str
    settlement_type: str
    refund_status: str
    created_at: datetime


class PurchaseReturnListOut(BaseModel):
    items: list[PurchaseReturnListItem]
    total: int
    page: int
    page_size: int


class PurchaseReturnPreviewItem(BaseModel):
    purchase_order_item_id: int
    sku_id: int
    sku_code: str
    sku_name: str
    product_name: str
    spec_values: dict[str, Any]
    ordered_quantity: int = Field(description="原采购计划数量，不能当作可退上限")
    received_quantity: int = Field(description="已经成功收货入库、可作为可退上限的数量")
    occupied_return_quantity: int = Field(
        description="有效未取消/未拒绝且非草稿采购退货已占用的退货数量",
    )
    returned_quantity: int = Field(description="历史已经真正出库退给供应商的数量")
    returnable_quantity: int = Field(description="当前还能再申请退货的数量")
    unit_price: float | None
    occupied_refund_amount: float
    refundable_amount: float = Field(description="当前还能再申请的供应商退款金额")
    inventory_quantity: int = Field(description="所选退货仓当前实际库存")
    inventory_reserved: int = Field(description="所选退货仓当前预占数量")
    inventory_available: int = Field(
        description="所选退货仓当前可用库存；确认出库时单次不能超过它",
    )


class PurchaseReturnPreviewOut(BaseModel):
    purchase_order_id: int
    purchase_order_no: str
    supplier_id: int
    supplier_name: str
    original_warehouse_id: int
    original_warehouse_name: str
    warehouse_id: int
    warehouse_name: str
    status: str
    eligible: bool
    items: list[PurchaseReturnPreviewItem]
