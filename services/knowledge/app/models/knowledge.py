"""知识库与文档元数据。V1 不实现上传；文档表为 V2 预留结构。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
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
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="知识库描述",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=KnowledgeBaseStatus.ACTIVE.value,
        comment="状态：ACTIVE 启用 / DISABLED 禁用",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="创建用户 ID，来自可信认证上下文",
    )
    updated_by: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="最近修改用户 ID",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="软删除时间；为空表示未删除",
    )

    documents: Mapped[list[KnowledgeDocument]] = relationship(
        back_populates="knowledge_base",
    )


class KnowledgeDocument(TimestampMixin, TenantMixin, Base):
    """知识库文档元数据。必须与所属知识库同租户，由复合外键约束。"""

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
        comment="对象存储键，V2 上传后写入",
    )
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小（字节）")
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="MIME 类型")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=KnowledgeDocumentStatus.PENDING.value,
        comment="解析状态：PENDING / PROCESSING / COMPLETED / FAILED",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="创建用户 ID，来自可信认证上下文",
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
