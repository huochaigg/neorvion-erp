from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="检索问题")
    knowledge_base_ids: list[int] | None = Field(default=None, description="限定知识库；空表示当前租户全部有权库")
    strategy: str = Field(default="HYBRID", description="VECTOR / KEYWORD / HYBRID")
    top_k: int = Field(default_factory=lambda: settings.default_top_k, ge=1, le=50)
    candidate_k: int = Field(default_factory=lambda: settings.default_candidate_k, ge=1, le=100)
    similarity_threshold: float | None = Field(default=None, ge=0, le=1, description="仅向量路使用的余弦相似度下限")
    vector_k: int | None = Field(default=None, ge=1, le=100, description="向量路召回条数，默认 candidate_k")
    keyword_k: int | None = Field(default=None, ge=1, le=100, description="关键词路召回条数，默认 candidate_k")
    rrf_k: int | None = Field(default=None, ge=1, le=200, description="RRF 常数 k，默认配置 rrf_k")
    rerank: bool = False

    @field_validator("strategy")
    @classmethod
    def normalize_strategy(cls, value: str) -> str:
        return value.strip().upper()


class SearchHitOut(BaseModel):
    chunk_id: int
    document_id: int
    knowledge_base_id: int
    filename: str
    content: str
    page_no: int | None
    heading: str | None
    chunk_index: int
    version: int
    final_rank: int
    vector_score: float | None = Field(default=None, description="余弦相似度 0-1，不是距离")
    keyword_score: float | None = Field(default=None, description="FTS/trigram 分，不是 BM25")
    rrf_score: float | None = Field(default=None, description="RRF 融合分")
    rerank_score: float | None = None


class SearchOut(BaseModel):
    items: list[SearchHitOut]
    strategy: str
    rerank_applied: bool
    rerank_degraded: bool
    stages: dict[str, Any]
    latency_ms: int
    knowledge_base_ids: list[int]


class RetrievalTestOut(SearchOut):
    pass


class IndexStatusOut(BaseModel):
    knowledge_base_id: int
    model_name: str
    dimensions: int
    total_active_chunks: int
    ready: int
    pending: int
    stale: int
    failed: int


class ConversationCreateIn(BaseModel):
    title: str | None = Field(default=None, max_length=128)
    knowledge_base_ids: list[int] | None = None


class ConversationOut(BaseModel):
    id: int
    tenant_id: int
    title: str
    knowledge_base_ids: list[int]
    created_by: int
    created_at: datetime
    updated_at: datetime


class ConversationListOut(BaseModel):
    items: list[ConversationOut]
    total: int
    page: int
    page_size: int


class CitationOut(BaseModel):
    chunk_id: int
    document_id: int
    knowledge_base_id: int
    filename: str
    page_no: int | None
    heading: str | None
    snippet: str
    rank: int
    vector_score: float | None = None
    keyword_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    status: str
    retrieval_strategy: str | None
    usage: dict[str, Any] | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime
    citations: list[CitationOut] = Field(default_factory=list)


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class ChatAskIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    strategy: str = Field(default="HYBRID")
    top_k: int | None = Field(default=None, ge=1, le=20)
    rerank: bool = True
    regenerate_of: int | None = Field(default=None, description="重新生成时指向原助手消息 ID")

    @field_validator("strategy")
    @classmethod
    def normalize_strategy(cls, value: str) -> str:
        return value.strip().upper()


class ModelProfileOut(BaseModel):
    id: int | None
    kind: str
    name: str
    provider: str
    base_url: str
    model_name: str
    dimensions: int | None
    api_key_env: str
    has_api_key: bool
    is_default: bool
    enabled: bool
    is_system: bool
    last_tested_at: datetime | None
    last_test_ok: bool | None
    last_test_message: str | None


class ModelTestIn(BaseModel):
    kind: str = Field(description="CHAT / EMBEDDING / RERANK")
