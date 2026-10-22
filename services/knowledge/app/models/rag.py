"""V3 RAG：向量、会话、引用、检索日志与平台模型配置。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class EmbeddingStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    STALE = "STALE"
    FAILED = "FAILED"


class RetrievalStrategy(StrEnum):
    VECTOR = "VECTOR"
    KEYWORD = "KEYWORD"
    HYBRID = "HYBRID"


class ModelKind(StrEnum):
    CHAT = "CHAT"
    EMBEDDING = "EMBEDDING"
    RERANK = "RERANK"


class MessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageStatus(StrEnum):
    STREAMING = "STREAMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ChunkEmbedding(TimestampMixin, TenantMixin, Base):
    """切片向量。检索只使用 READY 且模型/维度与当前配置一致的行。"""

    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_chunk_embeddings_tenant_id"),
        UniqueConstraint("tenant_id", "chunk_id", name="uq_chunk_embeddings_chunk"),
        ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["document_chunks.tenant_id", "document_chunks.id"],
            name="fk_chunk_embeddings_chunk_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_chunk_embeddings_document_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_chunk_embeddings_base_tenant",
        ),
        Index("ix_chunk_embeddings_tenant_base", "tenant_id", "knowledge_base_id"),
        Index("ix_chunk_embeddings_tenant_status", "tenant_id", "status", "model_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属知识库")
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属文档")
    chunk_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="对应切片")
    chunk_version: Mapped[int] = mapped_column(Integer, nullable=False, comment="写入时的切片版本")
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimensions),
        nullable=True,
        comment="向量；维度必须与 embedding_dimensions 一致",
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="生成该向量的 Embedding 模型")
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, comment="向量维度")
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="切片正文 SHA256，内容变化后必须重新索引",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=EmbeddingStatus.PENDING.value,
        comment="PENDING / READY / STALE / FAILED",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="最近索引失败原因")
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近一次成功写入向量的时间",
    )


class ModelProfile(TimestampMixin, Base):
    """平台级模型配置。密钥只引用环境变量名，API 响应不得返回密钥。"""

    __tablename__ = "model_profiles"
    __table_args__ = (UniqueConstraint("kind", "name", name="uq_model_profiles_kind_name"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, comment="CHAT / EMBEDDING / RERANK")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="配置显示名")
    provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="openai_compat",
        comment="openai_compat 表示 OpenAI 兼容协议",
    )
    base_url: Mapped[str] = mapped_column(String(512), nullable=False, server_default="", comment="API Base URL")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="供应商模型名")
    dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="仅 Embedding 使用的维度")
    api_key_env: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="",
        comment="密钥所在环境变量名，不是密钥本身",
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="系统配置：租户管理员不能改密钥",
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="连通性测试摘要，不含密钥")


class Conversation(TimestampMixin, TenantMixin, Base):
    """知识问答会话。knowledge_base_ids 限制本会话可检索的库。"""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id"),
        Index("ix_conversations_tenant_user", "tenant_id", "created_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False, server_default="新对话", comment="会话标题")
    knowledge_base_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="允许检索的知识库 ID 列表；空表示当前租户全部有权库",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="创建用户 ID")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(TimestampMixin, TenantMixin, Base):
    """会话消息。流式生成期间 status=STREAMING，完成后写 citations。"""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_messages_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_messages_conversation_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_messages_tenant_conversation", "tenant_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, comment="USER / ASSISTANT")
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="", comment="消息正文")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=MessageStatus.COMPLETED.value,
        comment="STREAMING / COMPLETED / FAILED / CANCELLED",
    )
    retrieval_strategy: Mapped[str | None] = mapped_column(String(16), nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="token 用量等，不含密钥")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="端到端耗时毫秒")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class MessageCitation(TimestampMixin, TenantMixin, Base):
    """回答实际使用的切片引用，供溯源。"""

    __tablename__ = "message_citations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_message_citations_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            name="fk_message_citations_message_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_message_citations_tenant_message", "tenant_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading: Mapped[str | None] = mapped_column(String(512), nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    rank: Mapped[int] = mapped_column(Integer, nullable=False, comment="最终展示顺序，从 1 开始")
    vector_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="余弦相似度 0-1")
    keyword_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="关键词分，不是 BM25")
    rrf_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="RRF 融合分")
    rerank_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Rerank 模型分")


class RetrievalLog(TimestampMixin, TenantMixin, Base):
    """单次检索调试记录。问答与检索测试共用。"""

    __tablename__ = "retrieval_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_retrieval_logs_tenant_id"),
        Index("ix_retrieval_logs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    knowledge_base_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="top_k、阈值等")
    stages: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="各路召回排名、耗时、是否 rerank 降级",
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class QueryEmbeddingCache(TimestampMixin, TenantMixin, Base):
    """成功生成的查询向量。失败和维度不完整的结果不写入。"""

    __tablename__ = "query_embedding_cache"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cache_key", name="uq_query_embedding_cache_key"),
        Index("ix_query_embedding_cache_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="租户内查询向量缓存键")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, comment="Embedding Provider")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Embedding 模型")
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, comment="向量维度")
    embedding: Mapped[list] = mapped_column(JSONB, nullable=False, comment="完整查询向量")
    prompt_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="供应商返回的 Embedding Token；没有则留空",
    )


# 仅用于类型提示；实际 GIN 索引在迁移中创建。
_ = TSVECTOR
