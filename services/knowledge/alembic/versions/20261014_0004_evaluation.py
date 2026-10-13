"""Knowledge V4：评测数据集、实验与异步运行。

Revision ID: 20261014_0004
Revises: 20261013_0003
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261014_0004"
down_revision: str | None = "20261013_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="数据集名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="用途与标注说明"),
        sa.Column(
            "knowledge_base_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
            comment="关联知识库 ID 列表",
        ),
        sa.Column("current_version", sa.Integer(), server_default="0", nullable=False, comment="已冻结的最新版本号"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evaluation_datasets_tenant_id"),
    )
    op.create_index(
        "uq_evaluation_datasets_tenant_name_active",
        "evaluation_datasets",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "evaluation_dataset_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, comment="从 1 递增"),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="冻结时的问题与标注"),
        sa.Column("case_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ready_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unanswerable_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("stale_judgment_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evaluation_dataset_versions_tenant_id"),
        sa.UniqueConstraint("tenant_id", "dataset_id", "version", name="uq_evaluation_dataset_versions_ver"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_dataset_versions_dataset_tenant",
        ),
    )

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False, comment="评测问题"),
        sa.Column("expected_answer", sa.Text(), nullable=True, comment="标准答案；无答案题可为空"),
        sa.Column("question_type", sa.String(length=32), server_default="FACTUAL", nullable=False),
        sa.Column("difficulty", sa.Integer(), server_default="2", nullable=False, comment="1-5"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column(
            "is_unanswerable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="显式无答案题，不能当成缺少标注",
        ),
        sa.Column("annotation_status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("source", sa.String(length=16), server_default="MANUAL", nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evaluation_cases_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_cases_dataset_tenant",
        ),
    )
    op.create_index("ix_evaluation_cases_tenant_dataset", "evaluation_cases", ["tenant_id", "dataset_id"])
    op.create_index("ix_evaluation_cases_tenant_status", "evaluation_cases", ["tenant_id", "annotation_status"])

    op.create_table(
        "evaluation_judgments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), nullable=False),
        sa.Column("relevance", sa.Integer(), nullable=False, comment="相关性 0/1/2/3"),
        sa.Column("source_key", sa.String(length=256), nullable=False, comment="稳定来源键"),
        sa.Column("chunk_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), server_default="", nullable=False),
        sa.Column("snippet", sa.Text(), server_default="", nullable=False),
        sa.Column("stale", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evaluation_judgments_tenant_id"),
        sa.UniqueConstraint("tenant_id", "case_id", "chunk_id", name="uq_evaluation_judgments_case_chunk"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["evaluation_cases.tenant_id", "evaluation_cases.id"],
            name="fk_eval_judgments_case_tenant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_judgments_dataset_tenant",
        ),
    )
    op.create_index("ix_evaluation_judgments_tenant_case", "evaluation_judgments", ["tenant_id", "case_id"])

    op.create_table(
        "evaluation_experiments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="检索与生成参数方案"),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evaluation_experiments_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_experiments_dataset_tenant",
        ),
    )
    op.create_index("ix_evaluation_experiments_tenant_dataset", "evaluation_experiments", ["tenant_id", "dataset_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("experiment_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="QUEUED", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "dataset_snapshot_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evaluation_runs_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "experiment_id"],
            ["evaluation_experiments.tenant_id", "evaluation_experiments.id"],
            name="fk_eval_runs_experiment_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_runs_dataset_tenant",
        ),
    )
    op.create_index("ix_evaluation_runs_tenant_status", "evaluation_runs", ["tenant_id", "status"])
    op.create_index(
        "uq_evaluation_runs_active",
        "evaluation_runs",
        ["tenant_id", "experiment_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, comment="所属企业 ID，来自 ERP 已校验的租户上下文"),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("is_unanswerable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("retrieved", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("retrieval_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("generation_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("judge_model", sa.String(length=128), nullable=True),
        sa.Column("judge_prompt_version", sa.String(length=32), nullable=True),
        sa.Column("judge_raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("judge_error", sa.Text(), nullable=True),
        sa.Column("human_override", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evaluation_results_tenant_id"),
        sa.UniqueConstraint("tenant_id", "run_id", "case_id", name="uq_evaluation_results_run_case"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["evaluation_runs.tenant_id", "evaluation_runs.id"],
            name="fk_eval_results_run_tenant",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_evaluation_results_tenant_run", "evaluation_results", ["tenant_id", "run_id"])


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_experiments")
    op.drop_table("evaluation_judgments")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_dataset_versions")
    op.drop_table("evaluation_datasets")
