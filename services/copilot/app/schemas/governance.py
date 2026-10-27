from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

MODEL_PURPOSES = {
    "CHAT",
    "TOOL_CALLING",
    "MULTI_AGENT",
    "INSIGHT_ANALYSIS",
    "EVALUATION_JUDGE",
}


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z0-9_-]{2,64}$")
    display_name: str = Field(min_length=2, max_length=100)
    base_url: HttpUrl
    secret_env_name: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,99}$")
    data_region: str = Field(default="UNKNOWN", max_length=32)


class ProviderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    base_url: HttpUrl | None = None
    secret_env_name: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,99}$")
    data_region: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|DISABLED)$")


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    display_name: str
    base_url: str
    secret_env_name: str
    secret_configured: bool = Field(description="仅表示部署环境存在密钥，不返回密钥内容")
    status: str
    data_region: str
    last_probe_status: str
    last_probe_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=128)
    purposes: list[str] = Field(min_length=1)
    enabled: bool = False
    supports_tools: bool = True
    context_window: int = Field(ge=1024, le=2_000_000)
    max_output_tokens: int = Field(ge=128, le=131_072)
    pricing_version: str | None = Field(default=None, max_length=64)
    input_price: Decimal | None = Field(default=None, ge=0)
    output_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    unit_tokens: int = Field(default=1_000_000, ge=1)

    @field_validator("purposes")
    @classmethod
    def valid_purposes(cls, value: list[str]) -> list[str]:
        normalized = sorted(set(item.upper() for item in value))
        if not set(normalized).issubset(MODEL_PURPOSES):
            raise ValueError("模型用途不在允许目录")
        return normalized


class ModelOut(ModelCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class GovernancePolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_provider_codes: list[str] = Field(default_factory=list)
    allowed_model_names: list[str] = Field(default_factory=list)
    allowed_agents: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    multi_agent_enabled: bool = True
    insight_analysis_enabled: bool = False
    live_evaluation_enabled: bool = False
    max_context_tokens: int = Field(default=6000, ge=512, le=100_000)
    trace_retention_days: int = Field(default=90, ge=7, le=3650)
    conversation_retention_days: int = Field(default=365, ge=30, le=3650)


class GovernancePolicyOut(GovernancePolicyIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_by: int
    updated_at: datetime


class TenantQuotaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests_per_minute: int = Field(default=30, ge=1, le=10_000)
    requests_per_day: int = Field(default=1000, ge=1, le=10_000_000)
    monthly_token_limit: int = Field(default=1_000_000, ge=1)
    monthly_budget: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=8)
    max_concurrent_agents: int = Field(default=3, ge=1, le=100)
    max_concurrent_evaluations: int = Field(default=1, ge=1, le=20)
    insight_monthly_token_limit: int = Field(default=200_000, ge=0)
    max_tool_calls_per_request: int = Field(default=8, ge=1, le=100)
    max_execution_seconds: int = Field(default=60, ge=5, le=3600)
    warning_threshold_percent: int = Field(default=80, ge=1, le=100)
    hard_limit: bool = True


class TenantQuotaOut(TenantQuotaIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_by: int
    updated_at: datetime


class RetentionPreviewIn(BaseModel):
    dry_run: bool = Field(default=True, description="V11 API 仅允许 dry-run，不直接物理删除")


class GovernanceAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_user_id: int | None
    actor_type: str
    action: str
    target_type: str
    target_id: str
    outcome: str
    safe_detail: dict
    request_id: str
    created_at: datetime
