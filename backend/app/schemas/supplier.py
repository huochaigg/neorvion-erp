from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    code: str | None = Field(default=None, max_length=32)
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: str | None = Field(default=None, max_length=128)
    country_code: str | None = Field(default=None, max_length=2)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("供应商名称不能为空")
        return name

    @field_validator(
        "code",
        "contact_name",
        "contact_phone",
        "contact_email",
        "province",
        "city",
        "address",
        "remark",
    )
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("status", "country_code")
    @classmethod
    def normalize_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper()
        return text or None


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: str | None = Field(default=None, max_length=128)
    country_code: str | None = Field(default=None, max_length=2)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("供应商名称不能为空")
        return name

    @field_validator(
        "contact_name",
        "contact_phone",
        "contact_email",
        "province",
        "city",
        "address",
        "remark",
    )
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("country_code")
    @classmethod
    def normalize_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper()
        return text or None

    @model_validator(mode="after")
    def require_field(self) -> SupplierUpdate:
        if not self.model_fields_set:
            raise ValueError("请提供要修改的字段")
        return self


class SupplierStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=16)

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return value.strip().upper()


class SupplierOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    country_code: str | None
    province: str | None
    city: str | None
    address: str | None
    status: str
    remark: str | None
    created_at: datetime
    updated_at: datetime


class SupplierListOut(BaseModel):
    items: list[SupplierOut]
    total: int
    page: int
    page_size: int
