from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WarehouseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    code: str | None = Field(default=None, max_length=32)
    type: str = Field(min_length=1, max_length=16)
    country_code: str | None = Field(default=None, max_length=2)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    remark: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("仓库名称不能为空")
        return name

    @field_validator(
        "code",
        "province",
        "city",
        "address",
        "contact_name",
        "contact_phone",
        "remark",
    )
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("type", "status", "country_code")
    @classmethod
    def normalize_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper()
        return text or None


class WarehouseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    type: str | None = Field(default=None, max_length=16)
    country_code: str | None = Field(default=None, max_length=2)
    province: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    contact_name: str | None = Field(default=None, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    remark: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("仓库名称不能为空")
        return name

    @field_validator("province", "city", "address", "contact_name", "contact_phone", "remark")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("type", "country_code")
    @classmethod
    def normalize_upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper()
        return text or None

    @model_validator(mode="after")
    def require_field(self) -> WarehouseUpdate:
        if not self.model_fields_set:
            raise ValueError("请提供要修改的字段")
        return self


class WarehouseStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(min_length=1, max_length=16)

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        return value.strip().upper()


class WarehouseOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    type: str
    country_code: str | None
    province: str | None
    city: str | None
    address: str | None
    contact_name: str | None
    contact_phone: str | None
    is_default: bool
    status: str
    remark: str | None
    created_at: datetime
    updated_at: datetime


class WarehouseListOut(BaseModel):
    items: list[WarehouseOut]
    total: int
    page: int
    page_size: int
