from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class GrantCreateIn(BaseModel):
    user_id: int = Field(gt=0, description="IAM 用户 ID")
    permission: str = Field(default="READ", description="READ / WRITE / ADMIN")

    @field_validator("permission")
    @classmethod
    def normalize_permission(cls, value: str) -> str:
        permission = value.strip().upper()
        if permission not in {"READ", "WRITE", "ADMIN"}:
            raise ValueError("授权级别必须是 READ、WRITE 或 ADMIN")
        return permission


class GrantOut(BaseModel):
    id: int
    knowledge_base_id: int
    user_id: int
    permission: str
    created_by: int
    created_at: datetime


class GrantListOut(BaseModel):
    items: list[GrantOut]
    restricted: bool = Field(description="true 表示该库启用了授权名单")


class RevisionOut(BaseModel):
    id: int
    document_id: int
    revision: int
    filename: str
    sha256: str
    file_size: int
    mime_type: str
    chunk_version: int
    note: str | None
    created_by: int
    created_at: datetime


class RevisionListOut(BaseModel):
    items: list[RevisionOut]


class RecycleItemOut(BaseModel):
    resource_type: str = Field(description="knowledge_base / document")
    id: int
    knowledge_base_id: int | None = None
    name: str
    deleted_at: datetime
    deleted_by: int | None = None


class RecycleListOut(BaseModel):
    items: list[RecycleItemOut]
    total: int
    page: int
    page_size: int


class RecycleTargetIn(BaseModel):
    resource_type: str = Field(description="knowledge_base / document")
    id: int = Field(gt=0)

    @field_validator("resource_type")
    @classmethod
    def normalize_resource_type(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in {"knowledge_base", "document"}:
            raise ValueError("resource_type 只能是 knowledge_base 或 document")
        return normalized


class RecycleBatchIn(BaseModel):
    items: list[RecycleTargetIn] = Field(min_length=1, max_length=100)


class RecycleEmptyIn(BaseModel):
    confirm: bool = Field(description="必须为 true，表示已知不可恢复")
    expected_count: int = Field(ge=0, description="当前回收站条数，用于防止页面过期误清空")


class RecycleBatchOut(BaseModel):
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    remaining: int = 0
    errors: list[dict] = Field(default_factory=list)


class ApiKeyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128, description="用途名称")
    scopes: list[str] = Field(default_factory=lambda: ["search"], description="search / chat / stats")
    knowledge_base_ids: list[int] = Field(default_factory=list, description="空表示租户内已授权的全部知识库")
    expires_at: datetime | None = Field(default=None, description="过期时间，空表示不过期")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("名称不能为空")
        return name


class ApiKeyOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    prefix: str
    scopes: list[str]
    knowledge_base_ids: list[int]
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_by: int
    created_at: datetime


class ApiKeyCreatedOut(ApiKeyOut):
    api_key: str = Field(description="明文密钥，仅创建响应返回一次")


class ApiKeyListOut(BaseModel):
    items: list[ApiKeyOut]
    total: int
    page: int
    page_size: int


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: int | None
    actor_key_id: int | None
    action: str
    resource_type: str
    resource_id: int | None
    detail: dict | None
    ip_address: str | None
    request_id: str | None
    created_at: datetime


class AuditLogListOut(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int


class ProbeIn(BaseModel):
    strategy: str = Field(default="HYBRID", description="VECTOR / KEYWORD / HYBRID")
    top_k: int = Field(default=8, ge=1, le=50)
    rerank: bool = False
    generate: bool = Field(default=False, description="是否调用生成模型；单题调试可关")
    knowledge_base_ids: list[int] | None = None


class ProbeOut(BaseModel):
    case_id: int
    question: str
    expected_answer: str | None = None
    is_unanswerable: bool
    strategy: str
    rerank_applied: bool
    rerank_degraded: bool
    latency_ms: int
    stages: dict
    retrieved: list[dict]
    retrieval_metrics: dict | None
    answer: str | None = None
    citations: list[dict] = Field(default_factory=list)
    usage: dict | None = None
    needs_human_review: bool = False
