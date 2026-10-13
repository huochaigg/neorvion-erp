"""知识库、文档、切片与处理任务。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class KnowledgeBaseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class KnowledgeDocumentStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChunkStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class TaskType(StrEnum):
    PARSE = "PARSE"
    CHUNK = "CHUNK"


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ChunkStrategy(StrEnum):
    FIXED = "FIXED"
    RECURSIVE = "RECURSIVE"


class KnowledgeBase(TimestampMixin, TenantMixin, Base):
    """企业知识库。同一租户下未删除记录的名称唯一。"""

    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_bases_tenant_id"),
        Index(
            "uq_knowledge_bases_tenant_name_active",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_knowledge_bases_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="知识库名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="知识库描述")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=KnowledgeBaseStatus.ACTIVE.value,
        comment="状态：ACTIVE 启用 / DISABLED 禁用",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="创建用户 ID")
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="最近修改用户 ID")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="软删除时间；为空表示未删除",
    )

    documents: Mapped[list[KnowledgeDocument]] = relationship(back_populates="knowledge_base")


class KnowledgeDocument(TimestampMixin, TenantMixin, Base):
    """知识库文档。原文件落磁盘，库内只存元数据与抽取文本。"""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_documents_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_knowledge_documents_base_tenant",
        ),
        Index("ix_knowledge_documents_tenant_base", "tenant_id", "knowledge_base_id"),
        Index("ix_knowledge_documents_tenant_status", "tenant_id", "status"),
        Index(
            "uq_knowledge_documents_sha256_active",
            "tenant_id",
            "knowledge_base_id",
            "sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND sha256 <> ''"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="所属知识库 ID，必须与 tenant_id 同属一家企业",
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    storage_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="相对存储根目录的安全路径，禁止用户可控绝对路径",
    )
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小（字节）")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="声明的 MIME 类型")
    extension: Mapped[str] = mapped_column(String(16), nullable=False, server_default="", comment="规范化扩展名")
    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="",
        comment="文件内容 SHA256，用于同库去重",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=KnowledgeDocumentStatus.PENDING.value,
        comment="流水线状态：PENDING / PROCESSING / COMPLETED / FAILED",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="最近一次失败原因")
    warning_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="解析限制提示，例如扫描版 PDF 无文本",
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True, comment="清洗后的抽取文本")
    extract_meta: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="页码、标题、来源等解析元数据",
    )
    chunk_strategy: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="最近一次切片策略 FIXED / RECURSIVE",
    )
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="切片长度，单位见 chunk_unit")
    chunk_overlap: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="切片重叠长度")
    chunk_unit: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="char",
        comment="切片长度单位：char 表示字符，不是 Token",
    )
    active_chunk_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="当前对外可见的切片版本",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="上传用户 ID")
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="最近修改用户 ID")
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="软删除时间；删除后释放 SHA256 占用",
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document")
    tasks: Mapped[list[DocumentProcessingTask]] = relationship(back_populates="document")


class DocumentChunk(TimestampMixin, TenantMixin, Base):
    """文档切片。仅 ACTIVE 且版本等于文档 active_chunk_version 的切片可被检索准备。"""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_document_chunks_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_document_chunks_document_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_document_chunks_base_tenant",
        ),
        Index("ix_document_chunks_tenant_document", "tenant_id", "document_id", "version"),
        Index("ix_document_chunks_tenant_base", "tenant_id", "knowledge_base_id"),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "version",
            "chunk_index",
            name="uq_document_chunks_doc_version_index",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属知识库")
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属文档")
    version: Mapped[int] = mapped_column(Integer, nullable=False, comment="切片批次版本")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="文档内顺序，从 0 开始")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="切片正文，字符级")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="字符数")
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源页码，从 1 开始")
    heading: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="最近标题")
    source_start: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="原文起始字符偏移")
    source_end: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="原文结束字符偏移")
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="额外溯源元数据")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=ChunkStatus.DRAFT.value,
        comment="DRAFT 未发布 / ACTIVE 可用 / SUPERSEDED 被新版本替换",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="启停。停用后 V3 检索不得使用",
    )
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="最近编辑用户")

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class DocumentProcessingTask(TimestampMixin, TenantMixin, Base):
    """解析 / 切片任务。数据库是状态真相，Redis 只投递 task id。"""

    __tablename__ = "document_processing_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_document_processing_tasks_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_document_tasks_document_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_document_tasks_base_tenant",
        ),
        Index("ix_document_tasks_tenant_document", "tenant_id", "document_id"),
        Index("ix_document_tasks_tenant_status", "tenant_id", "status"),
        Index(
            "uq_document_tasks_active",
            "tenant_id",
            "document_id",
            "task_type",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属知识库")
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属文档")
    task_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="PARSE 解析 / CHUNK 切片")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=TaskStatus.QUEUED.value,
        comment="QUEUED / RUNNING / SUCCESS / FAILED",
    )
    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="0-100 进度",
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", comment="尝试次数")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="切片参数等任务入参")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="创建用户 ID")

    document: Mapped[KnowledgeDocument] = relationship(back_populates="tasks")
