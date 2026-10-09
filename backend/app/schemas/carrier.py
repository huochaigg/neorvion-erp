from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


class CarrierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    code: str | None = Field(default=None, max_length=32)
    carrier_type: str = Field(min_length=1, max_length=32)
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    website: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("物流商名称不能为空")
        return name

    @field_validator("code", "contact_name", "contact_phone", "website", "remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        return _blank(value)

    @field_validator("carrier_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().upper()


class CarrierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    carrier_type: str | None = Field(default=None, min_length=1, max_length=32)
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    website: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("物流商名称不能为空")
        return name

    @field_validator("contact_name", "contact_phone", "website", "remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        return _blank(value)

    @field_validator("carrier_type")
    @classmethod
    def normalize_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @model_validator(mode="after")
    def require_field(self) -> CarrierUpdate:
        if not self.model_fields_set:
            raise ValueError("请提供要修改的字段")
        return self


class CarrierStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=16)

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return value.strip().upper()


class CarrierOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    carrier_type: str
    contact_name: str | None
    contact_phone: str | None
    website: str | None
    status: str
    remark: str | None
    created_at: datetime
    updated_at: datetime


class CarrierListOut(BaseModel):
    items: list[CarrierOut]
    total: int
    page: int
    page_size: int
