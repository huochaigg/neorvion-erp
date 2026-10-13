"""Knowledge V3：pgvector、关键词索引、会话与检索日志。

Revision ID: 20261013_0003
Revises: 20261013_0002
Create Date: 2026-10-13
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "20261013_0003"
down_revision: str | None = "20261013_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DIM = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column(
        "document_chunks",
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(content, ''))", persisted=True),
            nullable=True,
            comment="简单分词全文向量，中文主要靠 trigram，不是 BM25",
        ),
    )
    op.create_index(
        "ix_document_chunks_search_tsv",
        "document_chunks",
        ["search_tsv"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_chunks_content_trgm",
        "document_chunks",
        ["content"],
        postgresql_using="gin",
        postgresql_ops={"content": "gin_trgm_ops"},
    )

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False, comment="所属知识库"),
        sa.Column("document_id", sa.BigInteger(), nullable=False, comment="所属文档"),
        sa.Column("chunk_id", sa.BigInteger(), nullable=False, comment="对应切片"),
        sa.Column("chunk_version", sa.Integer(), nullable=False, comment="写入时的切片版本"),
        sa.Column("embedding", Vector(_DIM), nullable=True, comment="向量"),
        sa.Column("model_name", sa.String(length=128), nullable=False, comment="生成该向量的 Embedding 模型"),
        sa.Column("dimensions", sa.Integer(), nullable=False, comment="向量维度"),
        sa.Column("content_hash", sa.String(length=64), nullable=False, comment="切片正文 SHA256"),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
            comment="PENDING / READY / STALE / FAILED",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_chunk_embeddings_tenant_id"),
        sa.UniqueConstraint("tenant_id", "chunk_id", name="uq_chunk_embeddings_chunk"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "chunk_id"],
            ["document_chunks.tenant_id", "document_chunks.id"],
            name="fk_chunk_embeddings_chunk_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_chunk_embeddings_document_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_chunk_embeddings_base_tenant",
        ),
    )
    op.create_index("ix_chunk_embeddings_tenant_base", "chunk_embeddings", ["tenant_id", "knowledge_base_id"])
    op.create_index(
        "ix_chunk_embeddings_tenant_status",
        "chunk_embeddings",
        ["tenant_id", "status", "model_name"],
    )

    op.create_table(
        "model_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, comment="CHAT / EMBEDDING / RERANK"),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="openai_compat", nullable=False),
        sa.Column("base_url", sa.String(length=512), server_default="", nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=True),
        sa.Column("api_key_env", sa.String(length=64), server_default="", nullable=False, comment="密钥环境变量名"),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "name", name="uq_model_profiles_kind_name"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=128), server_default="新对话", nullable=False),
        sa.Column("knowledge_base_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id"),
    )
    op.create_index("ix_conversations_tenant_user", "conversations", ["tenant_id", "created_by"])
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="COMPLETED", nullable=False),
        sa.Column("retrieval_strategy", sa.String(length=16), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_messages_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_messages_conversation_tenant",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_messages_tenant_conversation", "messages", ["tenant_id", "conversation_id"])
    op.create_index("ix_messages_tenant_id", "messages", ["tenant_id"])

    op.create_table(
        "message_citations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.String(length=255), server_default="", nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("heading", sa.String(length=512), nullable=True),
        sa.Column("snippet", sa.Text(), server_default="", nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("keyword_score", sa.Float(), nullable=True),
        sa.Column("rrf_score", sa.Float(), nullable=True),
        sa.Column("rerank_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_message_citations_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            name="fk_message_citations_message_tenant",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_message_citations_tenant_message", "message_citations", ["tenant_id", "message_id"])
    op.create_index("ix_message_citations_tenant_id", "message_citations", ["tenant_id"])

    op.create_table(
        "retrieval_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("conversation_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("strategy", sa.String(length=16), nullable=False),
        sa.Column("knowledge_base_ids", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_retrieval_logs_tenant_id"),
    )
    op.create_index("ix_retrieval_logs_tenant_created", "retrieval_logs", ["tenant_id", "created_at"])
    op.create_index("ix_retrieval_logs_tenant_id", "retrieval_logs", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("retrieval_logs")
    op.drop_table("message_citations")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("model_profiles")
    op.drop_table("chunk_embeddings")
    op.drop_index("ix_document_chunks_content_trgm", table_name="document_chunks")
    op.drop_index("ix_document_chunks_search_tsv", table_name="document_chunks")
    op.drop_column("document_chunks", "search_tsv")
