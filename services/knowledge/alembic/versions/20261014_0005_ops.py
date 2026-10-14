"""Knowledge V5：文档版本、回收站、知识库授权、API Key、审计；评测题幂等键。

Revision ID: 20261014_0005
Revises: 20261014_0004
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261014_0005"
down_revision: str | None = "20261014_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_cases",
        sa.Column("external_key", sa.String(length=64), nullable=True, comment="导入幂等键，租户+数据集内唯一"),
    )
    op.add_column(
        "evaluation_cases",
        sa.Column(
            "needs_human_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="AI 生成的标准答案/标注，不能直接当正式基准",
        ),
    )
    op.create_index(
        "uq_evaluation_cases_external_key",
        "evaluation_cases",
        ["tenant_id", "dataset_id", "external_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND external_key IS NOT NULL"),
    )

    op.create_table(
        "document_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID"),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, comment="从 1 递增的文件版本号"),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False, comment="快照文件相对路径"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("chunk_version", sa.Integer(), nullable=False, server_default="0", comment="快照时的 active_chunk_version"),
        sa.Column("note", sa.Text(), nullable=True, comment="版本说明"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_document_revisions_document_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_document_revisions_tenant_id"),
        sa.UniqueConstraint("tenant_id", "document_id", "revision", name="uq_document_revisions_ver"),
    )
    op.create_index("ix_document_revisions_tenant_document", "document_revisions", ["tenant_id", "document_id"])

    op.create_table(
        "knowledge_base_grants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID"),
        sa.Column("knowledge_base_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="ERP 用户 ID"),
        sa.Column(
            "permission",
            sa.String(length=16),
            nullable=False,
            server_default="READ",
            comment="READ 只读 / WRITE 可改 / ADMIN 可授权",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_knowledge_base_grants_base_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_base_grants_tenant_id"),
        sa.UniqueConstraint("tenant_id", "knowledge_base_id", "user_id", name="uq_knowledge_base_grants_user"),
    )
    op.create_index("ix_knowledge_base_grants_tenant_user", "knowledge_base_grants", ["tenant_id", "user_id"])

    op.create_table(
        "knowledge_api_keys",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="用途名称"),
        sa.Column("prefix", sa.String(length=16), nullable=False, comment="明文前缀，便于识别，不是完整密钥"),
        sa.Column("key_hash", sa.String(length=64), nullable=False, comment="SHA256(hex)"),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"search\"]'::jsonb"),
            comment="search / chat / stats",
        ),
        sa.Column(
            "knowledge_base_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="空表示租户内已授权的全部知识库",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_api_keys_tenant_id"),
        sa.UniqueConstraint("key_hash", name="uq_knowledge_api_keys_hash"),
    )
    op.create_index("ix_knowledge_api_keys_tenant_prefix", "knowledge_api_keys", ["tenant_id", "prefix"])

    op.create_table(
        "knowledge_audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID"),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_key_id", sa.BigInteger(), nullable=True, comment="API Key 主键，可空"),
        sa.Column("action", sa.String(length=64), nullable=False, comment="稳定动作编码"),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.BigInteger(), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="已脱敏的上下文"),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_audit_logs_tenant_id"),
    )
    op.create_index("ix_knowledge_audit_logs_tenant_created", "knowledge_audit_logs", ["tenant_id", "created_at"])
    op.create_index(
        "ix_knowledge_audit_logs_tenant_resource",
        "knowledge_audit_logs",
        ["tenant_id", "resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_audit_logs")
    op.drop_table("knowledge_api_keys")
    op.drop_table("knowledge_base_grants")
    op.drop_table("document_revisions")
    op.drop_index("uq_evaluation_cases_external_key", table_name="evaluation_cases")
    op.drop_column("evaluation_cases", "needs_human_review")
    op.drop_column("evaluation_cases", "external_key")
