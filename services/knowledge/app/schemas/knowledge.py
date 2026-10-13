from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KnowledgeBaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128, description="知识库名称")
    description: str | None = Field(default=None, max_length=2000, description="知识库描述")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("知识库名称不能为空")
        return name

    @field_validator("description")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class KnowledgeBaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128, description="知识库名称")
    description: str | None = Field(default=None, max_length=2000, description="知识库描述")
    status: str | None = Field(default=None, max_length=16, description="状态 ACTIVE / DISABLED")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("知识库名称不能为空")
        return name

    @field_validator("description")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper() or None

    @model_validator(mode="after")
    def require_field(self) -> KnowledgeBaseUpdate:
        if not self.model_fields_set:
            raise ValueError("请提供要修改的字段")
        return self


class KnowledgeBaseOut(BaseModel):
    id: int
    tenant_id: int = Field(description="所属企业 ID")
    name: str
    description: str | None
    status: str
    document_count: int = Field(description="当前知识库文档数量")
    created_by: int = Field(description="创建用户 ID")
    updated_by: int = Field(description="最近修改用户 ID")
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListOut(BaseModel):
    items: list[KnowledgeBaseOut]
    total: int
    page: int
    page_size: int
