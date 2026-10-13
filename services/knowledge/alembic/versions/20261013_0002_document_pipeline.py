"""Knowledge V2：文档元数据扩展、切片表与处理任务表。

Revision ID: 20261013_0002
Revises: 20261013_0001
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261013_0002"
down_revision: str | None = "20261013_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("extension", sa.String(length=16), server_default="", nullable=False, comment="规范化扩展名"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("sha256", sa.String(length=64), server_default="", nullable=False, comment="文件内容 SHA256，用于同库去重"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("error_message", sa.Text(), nullable=True, comment="最近一次失败原因"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("warning_message", sa.Text(), nullable=True, comment="解析限制提示，例如扫描版 PDF 无文本"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("extracted_text", sa.Text(), nullable=True, comment="清洗后的抽取文本"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("extract_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="页码、标题、来源等解析元数据"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("chunk_strategy", sa.String(length=32), nullable=True, comment="最近一次切片策略 FIXED / RECURSIVE"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("chunk_size", sa.Integer(), nullable=True, comment="切片长度，单位见 chunk_unit"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("chunk_overlap", sa.Integer(), nullable=True, comment="切片重叠长度"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column(
            "chunk_unit",
            sa.String(length=16),
            server_default="char",
            nullable=False,
            comment="切片长度单位：char 表示字符，不是 Token",
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("active_chunk_version", sa.Integer(), server_default="0", nullable=False, comment="当前对外可见的切片版本"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="最近修改用户 ID"),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="软删除时间；删除后释放 SHA256 占用"),
    )
    op.create_index(
        "uq_knowledge_documents_sha256_active",
        "knowledge_documents",
        ["tenant_id", "knowledge_base_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND sha256 <> ''"),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False, comment="所属知识库"),
        sa.Column("document_id", sa.BigInteger(), nullable=False, comment="所属文档"),
        sa.Column("version", sa.Integer(), nullable=False, comment="切片批次版本"),
        sa.Column("chunk_index", sa.Integer(), nullable=False, comment="文档内顺序，从 0 开始"),
        sa.Column("content", sa.Text(), nullable=False, comment="切片正文，字符级"),
        sa.Column("char_count", sa.Integer(), nullable=False, comment="字符数"),
        sa.Column("page_no", sa.Integer(), nullable=True, comment="来源页码，从 1 开始"),
        sa.Column("heading", sa.String(length=512), nullable=True, comment="最近标题"),
        sa.Column("source_start", sa.Integer(), nullable=True, comment="原文起始字符偏移"),
        sa.Column("source_end", sa.Integer(), nullable=True, comment="原文结束字符偏移"),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="额外溯源元数据"),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="DRAFT",
            nullable=False,
            comment="DRAFT 未发布 / ACTIVE 可用 / SUPERSEDED 被新版本替换",
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False, comment="启停。停用后 V3 检索不得使用"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="最近编辑用户"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="最近修改时间"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_document_chunks_base_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_document_chunks_document_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_chunks_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "version",
            "chunk_index",
            name="uq_document_chunks_doc_version_index",
        ),
    )
    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"])
    op.create_index("ix_document_chunks_tenant_document", "document_chunks", ["tenant_id", "document_id", "version"])
    op.create_index("ix_document_chunks_tenant_base", "document_chunks", ["tenant_id", "knowledge_base_id"])

    op.create_table(
        "document_processing_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False, comment="所属知识库"),
        sa.Column("document_id", sa.BigInteger(), nullable=False, comment="所属文档"),
        sa.Column("task_type", sa.String(length=16), nullable=False, comment="PARSE 解析 / CHUNK 切片"),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="QUEUED",
            nullable=False,
            comment="QUEUED / RUNNING / SUCCESS / FAILED",
        ),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False, comment="0-100 进度"),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False, comment="尝试次数"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="切片参数等任务入参"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False, comment="创建用户 ID"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, comment="最近修改时间"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_document_tasks_base_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_document_tasks_document_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_processing_tasks_tenant_id"),
    )
    op.create_index("ix_document_processing_tasks_tenant_id", "document_processing_tasks", ["tenant_id"])
    op.create_index(
        "ix_document_tasks_tenant_document",
        "document_processing_tasks",
        ["tenant_id", "document_id"],
    )
    op.create_index(
        "ix_document_tasks_tenant_status",
        "document_processing_tasks",
        ["tenant_id", "status"],
    )
    op.create_index(
        "uq_document_tasks_active",
        "document_processing_tasks",
        ["tenant_id", "document_id", "task_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_document_tasks_active", table_name="document_processing_tasks")
    op.drop_index("ix_document_tasks_tenant_status", table_name="document_processing_tasks")
    op.drop_index("ix_document_tasks_tenant_document", table_name="document_processing_tasks")
    op.drop_index("ix_document_processing_tasks_tenant_id", table_name="document_processing_tasks")
    op.drop_table("document_processing_tasks")
    op.drop_index("ix_document_chunks_tenant_base", table_name="document_chunks")
    op.drop_index("ix_document_chunks_tenant_document", table_name="document_chunks")
    op.drop_index("ix_document_chunks_tenant_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("uq_knowledge_documents_sha256_active", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "deleted_at")
    op.drop_column("knowledge_documents", "updated_by")
    op.drop_column("knowledge_documents", "active_chunk_version")
    op.drop_column("knowledge_documents", "chunk_unit")
    op.drop_column("knowledge_documents", "chunk_overlap")
    op.drop_column("knowledge_documents", "chunk_size")
    op.drop_column("knowledge_documents", "chunk_strategy")
    op.drop_column("knowledge_documents", "extract_meta")
    op.drop_column("knowledge_documents", "extracted_text")
    op.drop_column("knowledge_documents", "warning_message")
    op.drop_column("knowledge_documents", "error_message")
    op.drop_column("knowledge_documents", "sha256")
    op.drop_column("knowledge_documents", "extension")
