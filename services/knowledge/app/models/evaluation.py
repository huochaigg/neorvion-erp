"""V4 评测：数据集、标注、实验、运行结果。不改 V3 问答与索引表。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin


class QuestionType(StrEnum):
    FACTUAL = "FACTUAL"
    MULTI_CONDITION = "MULTI_CONDITION"
    MULTI_DOC = "MULTI_DOC"
    PARAPHRASE = "PARAPHRASE"
    MIXED_LANG = "MIXED_LANG"
    LONG = "LONG"
    UNANSWERABLE = "UNANSWERABLE"
    HALLUCINATION = "HALLUCINATION"


class AnnotationStatus(StrEnum):
    PENDING = "PENDING"
    LABELED = "LABELED"
    READY = "READY"


class CaseSource(StrEnum):
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"
    CHAT = "CHAT"
    AI_SEED = "AI_SEED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


ACTIVE_RUN_STATUSES = (RunStatus.QUEUED.value, RunStatus.RUNNING.value, RunStatus.PAUSED.value)


class EvaluationDataset(TimestampMixin, TenantMixin, Base):
    """评测数据集。正式评测必须使用已冻结的版本快照。"""

    __tablename__ = "evaluation_datasets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evaluation_datasets_tenant_id"),
        Index(
            "uq_evaluation_datasets_tenant_name_active",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="数据集名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用途与标注说明")
    knowledge_base_ids: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="关联知识库 ID 列表，检索时作为授权范围",
    )
    current_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="已冻结的最新版本号；0 表示尚未快照",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationDatasetVersion(TimestampMixin, TenantMixin, Base):
    """数据集冻结快照，保证历史实验可复现。"""

    __tablename__ = "evaluation_dataset_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evaluation_dataset_versions_tenant_id"),
        UniqueConstraint("tenant_id", "dataset_id", "version", name="uq_evaluation_dataset_versions_ver"),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_dataset_versions_dataset_tenant",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, comment="从 1 递增")
    snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="冻结时的问题、标准答案与标注，含 source_key",
    )
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unanswerable_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    stale_judgment_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="快照时已失效的标注数，调用方需人工确认",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class EvaluationCase(TimestampMixin, TenantMixin, Base):
    """评测问题。未标注且非无答案的问题不能进入有监督检索指标。"""

    __tablename__ = "evaluation_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evaluation_cases_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_cases_dataset_tenant",
        ),
        Index("ix_evaluation_cases_tenant_dataset", "tenant_id", "dataset_id"),
        Index("ix_evaluation_cases_tenant_status", "tenant_id", "annotation_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False, comment="评测问题")
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True, comment="标准答案；无答案题可为空")
    question_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=QuestionType.FACTUAL.value,
        comment="问题类型，见 QuestionType",
    )
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="2", comment="1-5")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment="自由标签")
    is_unanswerable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="显式无答案题，不能当成缺少标注",
    )
    annotation_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=AnnotationStatus.PENDING.value,
        comment="PENDING 待标注 / LABELED 已标 / READY 可正式评测",
    )
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=CaseSource.MANUAL.value,
        comment="MANUAL / IMPORT / CHAT / AI_SEED",
    )
    source_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="从问答导入时的消息 ID，仅作溯源",
    )
    external_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="导入幂等键，租户+数据集内唯一",
    )
    needs_human_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="AI 生成的标准答案/标注，不能直接当正式基准",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationJudgment(TimestampMixin, TenantMixin, Base):
    """问题与相关 Chunk 的标注。Chunk 版本变化后 stale=true，禁止悄悄当有效相关。"""

    __tablename__ = "evaluation_judgments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evaluation_judgments_tenant_id"),
        UniqueConstraint("tenant_id", "case_id", "chunk_id", name="uq_evaluation_judgments_case_chunk"),
        ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["evaluation_cases.tenant_id", "evaluation_cases.id"],
            name="fk_eval_judgments_case_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_judgments_dataset_tenant",
        ),
        Index("ix_evaluation_judgments_tenant_case", "tenant_id", "case_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    case_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="标注时的文档 ID")
    chunk_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="标注时的切片 ID")
    relevance: Mapped[int] = mapped_column(Integer, nullable=False, comment="相关性 0/1/2/3")
    source_key: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="稳定来源键：kb/doc/sha256/version/index，用于版本失效检测",
    )
    chunk_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="标注时正文 SHA256")
    filename: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    snippet: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    stale: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="切片被替换或内容变化后为 true，需人工重确认",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class EvaluationExperiment(TimestampMixin, TenantMixin, Base):
    """评测实验与可复用参数方案。"""

    __tablename__ = "evaluation_experiments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evaluation_experiments_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_experiments_dataset_tenant",
        ),
        Index("ix_evaluation_experiments_tenant_dataset", "tenant_id", "dataset_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="检索与生成参数方案，运行时再拷贝到 run.config_snapshot",
    )
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationRun(TimestampMixin, TenantMixin, Base):
    """一次异步评测执行。PostgreSQL 是状态真相。"""

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evaluation_runs_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "experiment_id"],
            ["evaluation_experiments.tenant_id", "evaluation_experiments.id"],
            name="fk_eval_runs_experiment_tenant",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_runs_dataset_tenant",
        ),
        Index("ix_evaluation_runs_tenant_status", "tenant_id", "status"),
        Index(
            "uq_evaluation_runs_active",
            "tenant_id",
            "experiment_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING', 'PAUSED')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False, comment="运行使用的冻结版本")
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=RunStatus.QUEUED.value,
        comment="QUEUED / RUNNING / PAUSED / SUCCESS / FAILED / CANCELLED",
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="0-100")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    pause_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    interrupt_reason: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="USER_PAUSE / TOKEN_BUDGET / RATE_LIMIT / WORKER_CRASH 等",
    )
    current_case_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="正在执行的题目")
    current_stage: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="正在执行的阶段")
    token_budget: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="本 Run Token 预算，可在恢复前调整")
    cost_budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True, comment="本 Run 费用预算，空表示不限制")
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="持有租约的 Worker")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="运行入参快照，含模型与语料版本")
    dataset_snapshot_meta: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="数据集版本元数据：题目数、失效标注数、是否严格可比",
    )
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="聚合指标，含粒度标记")
    usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="token、耗时、估算费用")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class EvaluationResult(TimestampMixin, TenantMixin, Base):
    """单题评测明细。检索结果与引用均为快照，不回写线上索引。"""

    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_evaluation_results_tenant_id"),
        UniqueConstraint("tenant_id", "run_id", "case_id", name="uq_evaluation_results_run_case"),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["evaluation_runs.tenant_id", "evaluation_runs.id"],
            name="fk_eval_results_run_tenant",
            ondelete="CASCADE",
        ),
        Index("ix_evaluation_results_tenant_run", "tenant_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    case_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="快照中的 case id")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    is_unanswerable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    retrieved: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    retrieval_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="本题 Chunk 粒度指标")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    judge_prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    judge_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="裁判原始 JSON，失败时为空")
    judge_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="裁判失败原因，不得伪造分数")
    human_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="人工复核分数")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    usage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="SUCCESS",
        comment="PENDING / SUCCESS / FAILED；历史已完成行视为 SUCCESS",
    )
    stages: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment="RETRIEVE/RERANK/GENERATE/JUDGE/METRICS 阶段状态与用量",
    )


class LabelJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SuggestionStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class LabelConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvaluationLabelSuggestion(TimestampMixin, TenantMixin, Base):
    """AI 初标草稿。确认前不写入正式标注，也不能把题目标成 READY。"""

    __tablename__ = "evaluation_label_suggestions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_eval_label_suggestions_tenant_id"),
        UniqueConstraint("tenant_id", "case_id", name="uq_eval_label_suggestions_case"),
        ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            ["evaluation_cases.tenant_id", "evaluation_cases.id"],
            name="fk_eval_label_suggestions_case_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_label_suggestions_dataset_tenant",
        ),
        Index("ix_eval_label_suggestions_dataset", "tenant_id", "dataset_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    case_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=SuggestionStatus.DRAFT.value,
        comment="DRAFT 待审核 / CONFIRMED 已确认 / REJECTED 已驳回 / FAILED 调用失败",
    )
    confidence: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=LabelConfidence.LOW.value,
        comment="HIGH/MEDIUM/LOW，只表示审核优先级，不是正确率",
    )
    verdict: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="INSUFFICIENT",
        comment="ANSWERABLE / UNANSWERABLE / PARTIAL / CONFLICT / INSUFFICIENT",
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    risk: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    items: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="当前建议切片。确认前不是正式 Ground Truth",
    )
    original_items: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
        comment="模型最初给出的切片，人工修改后仍保留",
    )
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class EvaluationLabelJob(TimestampMixin, TenantMixin, Base):
    """一次智能初标任务。HTTP 只负责入队，进度以这张表为准。"""

    __tablename__ = "evaluation_label_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_eval_label_jobs_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "dataset_id"],
            ["evaluation_datasets.tenant_id", "evaluation_datasets.id"],
            name="fk_eval_label_jobs_dataset_tenant",
        ),
        Index(
            "uq_eval_label_jobs_active",
            "tenant_id",
            "dataset_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=LabelJobStatus.QUEUED.value)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    drafted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
