from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class DatasetCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128, description="数据集名称")
    description: str | None = Field(default=None, max_length=4000)
    knowledge_base_ids: list[int] = Field(default_factory=list, description="关联知识库")


class DatasetUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    knowledge_base_ids: list[int] | None = None


class DatasetOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: str | None
    knowledge_base_ids: list[int]
    current_version: int
    pending_count: int = 0
    labeled_count: int = 0
    ready_count: int = 0
    total_cases: int = 0
    created_at: datetime
    updated_at: datetime


class DatasetListOut(BaseModel):
    items: list[DatasetOut]
    total: int
    page: int
    page_size: int


class CaseCreateIn(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    expected_answer: str | None = Field(default=None, description="标准答案；无答案题可空")
    question_type: str = Field(default="FACTUAL")
    difficulty: int = Field(default=2, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    is_unanswerable: bool = False
    external_key: str | None = Field(default=None, max_length=64, description="导入幂等键")
    needs_human_review: bool = Field(default=False, description="AI 生成内容需人工复核")

    @field_validator("question_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().upper()


class CaseUpdateIn(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=8000)
    expected_answer: str | None = None
    question_type: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = None
    is_unanswerable: bool | None = None
    needs_human_review: bool | None = None

    @field_validator("question_type")
    @classmethod
    def normalize_type(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class JudgmentIn(BaseModel):
    chunk_id: int
    relevance: int = Field(ge=0, le=3, description="相关性 0/1/2/3")


class JudgmentOut(BaseModel):
    id: int
    chunk_id: int
    document_id: int
    relevance: int
    source_key: str
    chunk_version: int
    filename: str
    snippet: str
    stale: bool


class CaseOut(BaseModel):
    id: int
    dataset_id: int
    question: str
    expected_answer: str | None
    question_type: str
    difficulty: int
    tags: list[str]
    is_unanswerable: bool
    annotation_status: str
    source: str
    external_key: str | None = None
    needs_human_review: bool = False
    judgments: list[JudgmentOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CaseUpsertIn(CaseCreateIn):
    judgments: list[JudgmentIn] = Field(default_factory=list, description="相关 Chunk 标注")


class CaseUpsertBatchIn(BaseModel):
    items: list[CaseUpsertIn] = Field(min_length=1, max_length=200)


class CaseUpsertResultOut(BaseModel):
    created: int
    updated: int
    skipped: int
    items: list[CaseOut] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


class CaseListOut(BaseModel):
    items: list[CaseOut]
    total: int
    page: int
    page_size: int


class ImportResultOut(BaseModel):
    succeeded: int
    failed: int
    errors: list[dict[str, Any]]


class ChatImportIn(BaseModel):
    conversation_id: int
    confirm: bool = Field(default=False, description="false 只生成候选；true 写入待标注问题")


class ExperimentConfigIn(BaseModel):
    strategy: str = "HYBRID"
    top_k: int = Field(default_factory=lambda: settings.default_top_k, ge=1, le=50)
    candidate_k: int = Field(default_factory=lambda: settings.default_candidate_k, ge=1, le=100)
    vector_k: int | None = Field(default=None, ge=1, le=100)
    keyword_k: int | None = Field(default=None, ge=1, le=100)
    rrf_k: int = Field(default_factory=lambda: settings.rrf_k, ge=1, le=200)
    similarity_threshold: float | None = Field(default=None, ge=0, le=1)
    rerank: bool = False
    evaluate_generation: bool = Field(default=False, description="是否调用生成与 Judge，会产生模型费用")
    token_budget: int | None = Field(default=None, ge=0, description="本 Run Token 预算；空则用服务默认值")
    cost_budget_usd: float | None = Field(default=None, ge=0, description="本 Run 费用预算；空表示不限制")
    knowledge_base_ids: list[int] | None = None

    @field_validator("strategy")
    @classmethod
    def normalize_strategy(cls, value: str) -> str:
        return value.strip().upper()


class ExperimentCreateIn(BaseModel):
    dataset_id: int
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    config: ExperimentConfigIn = Field(default_factory=ExperimentConfigIn)


class ExperimentUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    config: ExperimentConfigIn | None = None


class ExperimentOut(BaseModel):
    id: int
    dataset_id: int
    name: str
    description: str | None
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ExperimentLatestRunOut(BaseModel):
    """列表用最近一次运行摘要。指标缺失为 null，不用 0 冒充。"""

    id: int
    status: str
    progress: int
    dataset_id: int
    dataset_version: int
    error_message: str | None = None
    recall: float | None = Field(default=None, description="Recall@K，K 为该次运行最终 Top-K")
    mrr: float | None = None
    ndcg: float | None = Field(default=None, description="nDCG@K")
    hit_rate: float | None = Field(default=None, description="Hit@K")
    precision: float | None = None
    k: int | None = Field(default=None, description="指标截断 K，通常等于最终 Top-K")
    latency_p95_ms: float | None = None
    supervised_count: int | None = Field(default=None, description="参与检索指标宏平均的有效题目数")
    unanswerable_count: int | None = None
    case_count: int | None = Field(default=None, description="本次运行题目总数")
    comparable: bool | None = Field(default=None, description="数据集快照是否含失效标注")
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ExperimentListItemOut(ExperimentOut):
    """实验列表行：参数方案 + 最近一次运行的状态与真实指标。"""

    latest_run: ExperimentLatestRunOut | None = None


class ExperimentListOut(BaseModel):
    items: list[ExperimentListItemOut]
    total: int
    page: int
    page_size: int


class RunOut(BaseModel):
    id: int
    experiment_id: int
    dataset_id: int
    dataset_version: int
    status: str
    progress: int
    attempt: int
    error_message: str | None
    interrupt_reason: str | None = None
    current_case_id: int | None = None
    current_stage: str | None = None
    token_budget: int | None = None
    cost_budget_usd: float | None = None
    config_snapshot: dict[str, Any]
    dataset_snapshot_meta: dict[str, Any]
    metrics: dict[str, Any] | None
    usage: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class RunListOut(BaseModel):
    items: list[RunOut]
    total: int
    page: int
    page_size: int


class ResultOut(BaseModel):
    id: int
    run_id: int
    case_id: int
    question: str
    expected_answer: str | None = Field(default=None, description="快照中的标准答案，缺失则为空")
    is_unanswerable: bool
    retrieved: list[Any]
    retrieval_metrics: dict[str, Any] | None
    answer: str | None
    generation_metrics: dict[str, Any] | None
    judge_error: str | None
    human_override: dict[str, Any] | None
    latency_ms: int
    usage: dict[str, Any] | None = Field(default=None, description="本题 Token 与费用；未生成时为空")
    error_message: str | None
    result_status: str = "SUCCESS"
    stages: dict[str, Any] = Field(default_factory=dict)


class RunResumeIn(BaseModel):
    token_budget: int | None = Field(default=None, ge=0, description="恢复前可上调的 Token 预算")
    cost_budget_usd: float | None = Field(default=None, ge=0, description="恢复前可上调的费用预算")


class HumanOverrideIn(BaseModel):
    faithfulness: float | None = Field(default=None, ge=0, le=1)
    answer_relevancy: float | None = Field(default=None, ge=0, le=1)
    answer_correctness: float | None = Field(default=None, ge=0, le=1)
    note: str | None = Field(default=None, max_length=500)


class CompareOut(BaseModel):
    runs: list[RunOut]
    comparable: bool
    incomparable_reason: str | None = None
    metric_deltas: dict[str, Any]


class UsageStatsOut(BaseModel):
    query_count: int
    search_success: int
    search_empty: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float | None
    strategy_counts: dict[str, int]
    note: str
