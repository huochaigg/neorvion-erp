from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    parent_id: int | None = Field(default=None, gt=0)
    sort: int = Field(default=0, ge=0, le=9999)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("类目名称不能为空")
        return name


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    sort: int | None = Field(default=None, ge=0, le=9999)
    status: str | None = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("类目名称不能为空")
        return name

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @model_validator(mode="after")
    def require_field(self) -> CategoryUpdate:
        if self.name is None and self.sort is None and self.status is None:
            raise ValueError("请提供要修改的字段")
        return self


class CategoryOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    parent_id: int | None
    level: int
    sort: int
    status: str
    created_at: datetime
    updated_at: datetime
    children: list[CategoryOut] = Field(default_factory=list)


class BrandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=32)
    logo_url: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("品牌名称不能为空")
        return name

    @field_validator("logo_url", "description")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class BrandUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    logo_url: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("品牌名称不能为空")
        return name

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @model_validator(mode="after")
    def require_field(self) -> BrandUpdate:
        if (
            self.name is None
            and "logo_url" not in self.model_fields_set
            and "description" not in self.model_fields_set
            and self.status is None
        ):
            raise ValueError("请提供要修改的字段")
        return self


class BrandOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    logo_url: str | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class BrandListOut(BaseModel):
    items: list[BrandOut]
    total: int
    page: int
    page_size: int


class SkuInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_code: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    barcode: str | None = Field(default=None, max_length=64)
    spec_values: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default=None, max_length=16)

    @field_validator("sku_code")
    @classmethod
    def empty_sku_code_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("SKU 名称不能为空")
        return name

    @field_validator("barcode")
    @classmethod
    def strip_barcode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()


class SkuUpdate(BaseModel):
    """编辑已有 SKU。没有 sku_code 字段：创建后编码保持稳定。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    barcode: str | None = Field(default=None, max_length=64)
    spec_values: dict[str, Any] | None = None
    status: str | None = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("SKU 名称不能为空")
        return name

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @model_validator(mode="after")
    def require_field(self) -> SkuUpdate:
        if (
            self.name is None
            and "barcode" not in self.model_fields_set
            and self.spec_values is None
            and self.status is None
        ):
            raise ValueError("请提供要修改的字段")
        return self


class SkuOut(BaseModel):
    id: int
    tenant_id: int
    product_id: int
    sku_code: str
    name: str
    barcode: str | None
    spec_values: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    code: str | None = Field(default=None, max_length=64)
    category_id: int = Field(gt=0)
    brand_id: int | None = Field(default=None, gt=0)
    description: str | None = None
    status: str | None = Field(default=None, max_length=16)
    skus: list[SkuInput] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("商品名称不能为空")
        return name

    @field_validator("code")
    @classmethod
    def empty_code_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()


class ProductUpdate(BaseModel):
    """编辑已有商品。故意没有 code：没提交就保持原编码，禁止用空值重新生成。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    category_id: int | None = Field(default=None, gt=0)
    brand_id: int | None = Field(default=None, gt=0)
    description: str | None = None
    status: str | None = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("商品名称不能为空")
        return name

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()

    @model_validator(mode="after")
    def require_field(self) -> ProductUpdate:
        if (
            self.name is None
            and self.category_id is None
            and "brand_id" not in self.model_fields_set
            and "description" not in self.model_fields_set
            and self.status is None
        ):
            raise ValueError("请提供要修改的字段")
        return self


class ProductListItem(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    category_id: int
    category_name: str
    brand_id: int | None
    brand_name: str | None
    sku_count: int
    status: str
    created_at: datetime
    updated_at: datetime


class ProductListOut(BaseModel):
    items: list[ProductListItem]
    total: int
    page: int
    page_size: int


class ProductDetailOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    code: str
    category_id: int
    category_name: str
    brand_id: int | None
    brand_name: str | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    skus: list[SkuOut] = Field(default_factory=list)
