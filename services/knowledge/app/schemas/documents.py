from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings


class DocumentOut(BaseModel):
    id: int
    tenant_id: int
    knowledge_base_id: int
    filename: str
    file_size: int
    mime_type: str
    extension: str
    sha256: str
    status: str
    error_message: str | None
    warning_message: str | None
    extracted_char_count: int = Field(description="抽取文本字符数")
    chunk_strategy: str | None
    chunk_size: int | None = Field(default=None, description="切片长度，单位为字符")
    chunk_overlap: int | None
    chunk_unit: str = Field(description="切片单位，V2 固定为 char")
    active_chunk_version: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class DocumentDetailOut(DocumentOut):
    extracted_preview: str | None = Field(description="解析预览，最多 4000 字符")
    extract_meta: dict[str, Any] | None


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class UploadItemOut(BaseModel):
    filename: str
    ok: bool
    message: str
    document: DocumentOut | None = None


class UploadBatchOut(BaseModel):
    items: list[UploadItemOut]
    succeeded: int
    failed: int


class ChunkParamsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(default="RECURSIVE", description="FIXED 固定长度 / RECURSIVE 递归切分")
    chunk_size: int = Field(default_factory=lambda: settings.default_chunk_size, description="切片长度（字符）")
    chunk_overlap: int = Field(default_factory=lambda: settings.default_chunk_overlap, description="重叠长度（字符）")

    @field_validator("strategy")
    @classmethod
    def normalize_strategy(cls, value: str) -> str:
        return value.strip().upper()


class ChunkOut(BaseModel):
    id: int
    tenant_id: int
    knowledge_base_id: int
    document_id: int
    version: int
    chunk_index: int
    content: str
    char_count: int = Field(description="字符数，不是 Token")
    page_no: int | None
    heading: str | None
    source_start: int | None
    source_end: int | None
    status: str
    enabled: bool
    updated_at: datetime


class ChunkListOut(BaseModel):
    items: list[ChunkOut]
    total: int
    page: int
    page_size: int


class ChunkUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None, min_length=1, description="切片正文")
    enabled: bool | None = Field(default=None, description="是否对后续检索启用")

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("切片内容不能为空")
        return text

    @model_validator(mode="after")
    def require_field(self) -> ChunkUpdateIn:
        if not self.model_fields_set:
            raise ValueError("请提供要修改的字段")
        return self


class TaskOut(BaseModel):
    id: int
    tenant_id: int
    knowledge_base_id: int
    document_id: int
    task_type: str
    status: str
    progress: int
    attempt: int
    error_message: str | None
    payload: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    document_available: bool = Field(
        default=True,
        description="关联文档是否仍可打开；历史任务在文档回收后仍保留，此字段为 false",
    )


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int


class OverviewOut(BaseModel):
    knowledge_base_count: int
    document_count: int
    chunk_count: int
    document_completed: int
    document_failed: int
    pending_task_count: int
    failed_task_count: int
    recent_documents: list[DocumentOut]
    pending_tasks: list[TaskOut]
