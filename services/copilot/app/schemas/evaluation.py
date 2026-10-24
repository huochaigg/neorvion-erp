from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class EvaluationDatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, description="评测数据集名称")
    description: str | None = Field(
        default=None, max_length=2000, description="数据集用途与审核说明"
    )


class EvaluationDatasetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["DRAFT", "ACTIVE", "ARCHIVED"] | None = None


class EvaluationCaseCreate(BaseModel):
    external_key: str = Field(
        min_length=1, max_length=96, description="数据集内稳定且幂等的 Case 标识"
    )
    case_type: str = Field(min_length=1, max_length=64, description="业务场景分类")
    difficulty: int = Field(default=2, ge=1, le=5)
    user_input: str = Field(min_length=1, max_length=4000, description="送入 Agent 的用户问题")
    expected_behavior: dict[str, Any] = Field(description="结构化任务、拒绝或错误行为期望")
    expected_tools: dict[str, Any] = Field(
        default_factory=dict, description="必需、可选和禁止工具集合"
    )
    expected_arguments: list[dict[str, Any]] = Field(
        default_factory=list, description="工具参数谓词"
    )
    expected_evidence: dict[str, Any] = Field(
        default_factory=dict, description="证据类型、数量及权限断言"
    )
    expected_answer_assertions: list[dict[str, Any]] = Field(
        default_factory=list, description="可执行回答断言"
    )
    forbidden_actions: list[str] = Field(default_factory=list, description="绝不能执行的业务动作")
    required_permissions: list[str] = Field(
        default_factory=list, description="评测身份需要具备的真实 IAM 权限"
    )
    scenario_config: dict[str, Any] = Field(
        default_factory=dict, description="fixture、Replay 与故障注入配置"
    )
    status: Literal["READY", "NEEDS_REVIEW", "DISABLED"] = "NEEDS_REVIEW"

    @field_validator("expected_tools")
    @classmethod
    def validate_expected_tools(cls, value: dict[str, Any]) -> dict[str, Any]:
        allowed = {"required", "optional", "forbidden", "valid_sequences"}
        if set(value) - allowed:
            raise ValueError("expected_tools 包含未知字段")
        return value


class EvaluationCasePatch(BaseModel):
    case_type: str | None = Field(default=None, min_length=1, max_length=64)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    user_input: str | None = Field(default=None, min_length=1, max_length=4000)
    expected_behavior: dict[str, Any] | None = None
    expected_tools: dict[str, Any] | None = None
    expected_arguments: list[dict[str, Any]] | None = None
    expected_evidence: dict[str, Any] | None = None
    expected_answer_assertions: list[dict[str, Any]] | None = None
    forbidden_actions: list[str] | None = None
    required_permissions: list[str] | None = None
    scenario_config: dict[str, Any] | None = None
    status: Literal["READY", "NEEDS_REVIEW", "DISABLED"] | None = None


class EvaluationCaseImport(BaseModel):
    items: list[EvaluationCaseCreate] = Field(
        min_length=1, max_length=500, description="批量导入 Case"
    )


class EvaluationDatasetOut(BaseModel):
    id: int
    name: str
    description: str | None
    status: str
    current_version: int
    created_at: datetime
    updated_at: datetime


class EvaluationCaseOut(EvaluationCaseCreate):
    id: int
    dataset_id: int
    created_at: datetime
    updated_at: datetime


class EvaluationDatasetDetailOut(EvaluationDatasetOut):
    cases: list[EvaluationCaseOut] = Field(default_factory=list)


class EvaluationDatasetVersionOut(BaseModel):
    id: int
    dataset_id: int
    version: int
    content_hash: str
    case_count: int
    ready_count: int
    review_count: int
    frozen_at: datetime


class EvaluationRunCreate(BaseModel):
    dataset_version_id: int = Field(gt=0, description="必须指向不可变冻结版本")
    mode: Literal["SINGLE", "MULTI", "AUTO"]
    execution_kind: Literal["REPLAY", "LIVE"] = Field(
        default="REPLAY", description="REPLAY 使用冻结结果；LIVE 需要受控评测身份"
    )
    idempotency_key: str = Field(min_length=8, max_length=96)
    comparison_group: str | None = Field(default=None, max_length=64)
    token_budget: int | None = Field(default=None, ge=1)
    cost_budget: float | None = Field(default=None, ge=0)
    config: dict[str, Any] = Field(default_factory=dict, description="不可变运行配置补充项")


class EvaluationCaseRunOut(BaseModel):
    id: int
    case_key: str
    status: str
    task_outcome: str
    actual_answer: str | None
    metrics: dict[str, Any]
    assertion_results: list[dict[str, Any]]
    judge_model: str | None
    judge_prompt_version: str | None
    judge_feedback: dict[str, Any] | None
    judge_confidence: float | None
    human_override: dict[str, Any] | None
    error_code: int | None
    started_at: datetime | None
    finished_at: datetime | None


class EvaluationRunOut(BaseModel):
    id: int
    dataset_version_id: int
    mode: str
    execution_kind: str
    model_provider: str
    model_name: str
    environment_fingerprint: str
    status: str
    total_cases: int
    completed_cases: int
    failed_cases: int
    metrics: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class EvaluationRunDetailOut(EvaluationRunOut):
    cases: list[EvaluationCaseRunOut] = Field(default_factory=list)


class EvaluationComparisonCreate(BaseModel):
    baseline_run_id: int = Field(gt=0)
    candidate_run_id: int = Field(gt=0)


class EvaluationHumanReview(BaseModel):
    outcome: Literal["TASK_SUCCESS", "TASK_FAILED", "INDETERMINATE"]
    rationale: str = Field(min_length=3, max_length=2000, description="人工覆核理由，不得包含密钥")


class EvaluationComparisonOut(BaseModel):
    id: int
    baseline_run_id: int
    candidate_run_id: int
    comparable: bool
    incomparable_reason: str | None
    report: dict[str, Any]
    created_at: datetime


class AgentTraceOut(BaseModel):
    agent_run: dict[str, Any]
    tasks: list[dict[str, Any]]
    model_calls: list[dict[str, Any]]
    tool_runs: list[dict[str, Any]]
    evidences: list[dict[str, Any]]
