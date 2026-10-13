"""Knowledge V1：知识库与文档元数据表。

Revision ID: 20261013_0001
Revises:
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="知识库名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="知识库描述"),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="ACTIVE",
            nullable=False,
            comment="状态：ACTIVE 启用 / DISABLED 禁用",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False, comment="创建用户 ID，来自可信认证上下文"),
        sa.Column("updated_by", sa.BigInteger(), nullable=False, comment="最近修改用户 ID"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="最近修改时间",
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="软删除时间；为空表示未删除"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_bases_tenant_id"),
    )
    op.create_index("ix_knowledge_bases_tenant_id", "knowledge_bases", ["tenant_id"])
    op.create_index("ix_knowledge_bases_tenant_status", "knowledge_bases", ["tenant_id", "status"])
    op.create_index(
        "uq_knowledge_bases_tenant_name_active",
        "knowledge_bases",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column(
            "knowledge_base_id",
            sa.BigInteger(),
            nullable=False,
            comment="所属知识库 ID，必须与 tenant_id 同属一家企业",
        ),
        sa.Column("filename", sa.String(length=255), nullable=False, comment="原始文件名"),
        sa.Column("storage_key", sa.String(length=512), nullable=False, comment="对象存储键，V2 上传后写入"),
        sa.Column("file_size", sa.BigInteger(), nullable=False, comment="文件大小（字节）"),
        sa.Column("mime_type", sa.String(length=128), nullable=False, comment="MIME 类型"),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
            comment="解析状态：PENDING / PROCESSING / COMPLETED / FAILED",
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=False, comment="创建用户 ID，来自可信认证上下文"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="最近修改时间",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "knowledge_base_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.id"],
            name="fk_knowledge_documents_base_tenant",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_documents_tenant_id"),
    )
    op.create_index("ix_knowledge_documents_tenant_id", "knowledge_documents", ["tenant_id"])
    op.create_index(
        "ix_knowledge_documents_tenant_base",
        "knowledge_documents",
        ["tenant_id", "knowledge_base_id"],
    )
    op.create_index(
        "ix_knowledge_documents_tenant_status",
        "knowledge_documents",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_tenant_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_tenant_base", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_tenant_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("uq_knowledge_bases_tenant_name_active", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_tenant_status", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_tenant_id", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
