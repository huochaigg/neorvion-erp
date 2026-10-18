"""V5 运营能力：文档版本、知识库授权、API Key、审计。不改 V1–V4 主表结构。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class DocumentRevision(TimestampMixin, TenantMixin, Base):
    """文档文件版本快照。恢复时复制回 original，再排队解析；成功前旧 ACTIVE 切片仍可检索。"""

    __tablename__ = "document_revisions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_document_revisions_tenant_id"),
        UniqueConstraint("tenant_id", "document_id", "revision", name="uq_document_revisions_ver"),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_document_revisions_document_tenant",
        ),
        Index("ix_document_revisions_tenant_document", "tenant_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, comment="从 1 递增的文件版本号")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, comment="快照文件相对路径")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", comment="快照时的 active_chunk_version"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="版本说明")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class KnowledgeBaseGrant(TimestampMixin, TenantMixin, Base):
    """知识库级授权。有授权记录时仅名单内用户可访问；无记录则回退到租户 knowledge 权限。"""

    __tablename__ = "knowledge_base_grants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_base_grants_tenant_id"),
        UniqueConstraint("tenant_id", "knowledge_base_id", "user_id", name="uq_knowledge_base_grants_user"),
        ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_knowledge_base_grants_base_tenant",
        ),
        Index("ix_knowledge_base_grants_tenant_user", "tenant_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="IAM 用户 ID")
    permission: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="READ",
        comment="READ 只读 / WRITE 可改 / ADMIN 可授权",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class KnowledgeApiKey(TimestampMixin, TenantMixin, Base):
    """外部检索 API Key。明文只在创建时返回一次，库内仅保存 SHA256。"""

    __tablename__ = "knowledge_api_keys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_api_keys_tenant_id"),
        UniqueConstraint("key_hash", name="uq_knowledge_api_keys_hash"),
        Index("ix_knowledge_api_keys_tenant_prefix", "tenant_id", "prefix"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="用途名称")
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, comment="明文前缀，便于识别，不是完整密钥")
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="SHA256(hex)")
    scopes: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[\"search\"]'::jsonb"), comment="search / chat / stats"
    )
    knowledge_base_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment="空表示租户内已授权的全部知识库"
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class KnowledgeAuditLog(TimestampMixin, TenantMixin, Base):
    """知识库操作审计。禁止写入密码、Token、原文密钥。"""

    __tablename__ = "knowledge_audit_logs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_knowledge_audit_logs_tenant_id"),
        Index("ix_knowledge_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_knowledge_audit_logs_tenant_resource", "tenant_id", "resource_type", "resource_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_key_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="API Key 主键，可空")
    action: Mapped[str] = mapped_column(String(64), nullable=False, comment="稳定动作编码")
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="已脱敏的上下文")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
