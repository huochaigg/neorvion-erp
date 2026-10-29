from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class McpServerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    display_name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    transport_type: Literal["STREAMABLE_HTTP"] = "STREAMABLE_HTTP"
    endpoint: HttpUrl = Field(description="只允许治理白名单内的 HTTPS MCP Endpoint")
    authentication_type: Literal["NONE", "BEARER_ENV"] = "NONE"
    credential_reference: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{2,127}$",
        description="部署 Secret 环境变量名，不存储密钥内容",
    )
    allowed_tools: list[str] = Field(default_factory=list, max_length=200)
    denied_tools: list[str] = Field(default_factory=list, max_length=200)
    allowed_resources: dict[str, list[str]] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    max_retries: int = Field(default=1, ge=0, le=2)
    concurrency_limit: int = Field(default=2, ge=1, le=20)


class McpServerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    endpoint: HttpUrl | None = None
    authentication_type: Literal["NONE", "BEARER_ENV"] | None = None
    credential_reference: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    allowed_tools: list[str] | None = Field(default=None, max_length=200)
    denied_tools: list[str] | None = Field(default=None, max_length=200)
    allowed_resources: dict[str, list[str]] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=30)
    max_retries: int | None = Field(default=None, ge=0, le=2)
    concurrency_limit: int | None = Field(default=None, ge=1, le=20)


class McpServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    server_key: str
    display_name: str
    description: str
    transport_type: str
    endpoint: str
    authentication_type: str
    credential_reference: str | None
    credential_configured: bool = Field(description="只表示 Secret 是否存在，不返回 Secret")
    allowed_tools: list[str]
    denied_tools: list[str]
    allowed_resources: dict[str, Any]
    timeout_seconds: int
    max_retries: int
    concurrency_limit: int
    enabled: bool
    approval_status: str
    health_status: str
    last_checked_at: datetime | None
    configuration_version: int
    created_at: datetime
    updated_at: datetime


class McpApprovalIn(BaseModel):
    approved: bool


class McpToolReviewIn(BaseModel):
    approved: bool
    required_permissions: list[str] = Field(default_factory=list, max_length=30)
    resource_requirements: dict[str, list[str]] = Field(default_factory=dict)
    allowed_agents: list[str] = Field(default_factory=list, max_length=20)
    timeout_seconds: int = Field(default=10, ge=1, le=30)


class McpToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    server_id: int
    tool_name: str
    qualified_name: str
    description: str
    input_schema: dict[str, Any]
    schema_hash: str
    configuration_version: int
    required_permissions: list[str]
    resource_requirements: dict[str, Any]
    allowed_agents: list[str]
    risk_level: str
    timeout_seconds: int
    enabled: bool
    approval_status: str
    superseded_at: datetime | None
    created_at: datetime


class SkillVersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(
        min_length=10,
        max_length=12000,
        description="不可信业务指导文本，不具备代码执行或授权能力",
    )
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    allowed_agents: list[str] = Field(min_length=1, max_length=10)
    required_permissions: list[str] = Field(default_factory=list, max_length=30)
    allowed_tools: list[str] = Field(min_length=1, max_length=30)
    required_evidence: bool = True
    risk_level: Literal["READ_ONLY"] = "READ_ONLY"
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    token_budget: int = Field(default=3000, ge=256, le=20_000)

    @field_validator("instructions")
    @classmethod
    def reject_executable_content(cls, value: str) -> str:
        lowered = value.lower()
        forbidden = ("```python", "```sql", "```bash", "subprocess", "os.system", "eval(")
        if any(item in lowered for item in forbidden):
            raise ValueError("Skill 不允许包含可执行代码或命令")
        return value


class SkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_key: str = Field(pattern=r"^[a-z][a-z0-9-]{2,79}$")
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=5, max_length=1000)
    version: SkillVersionIn


class SkillVersionOut(SkillVersionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    skill_id: int
    version: int
    content_hash: str
    approval_status: str
    created_by: int
    created_at: datetime


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    skill_key: str
    name: str
    description: str
    current_version: int
    enabled: bool
    approval_status: str
    created_at: datetime
    updated_at: datetime


class SkillDetailOut(SkillOut):
    versions: list[SkillVersionOut] = Field(default_factory=list)


class SkillRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict[str, Any]
    idempotency_key: str = Field(min_length=8, max_length=96)
    conversation_id: int | None = Field(default=None, gt=0)


class SkillRollbackIn(BaseModel):
    version: int = Field(gt=0, description="要恢复的历史 Skill 版本号；恢复后仍需重新审核")


class SkillRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    skill_id: int
    skill_version: int
    status: str
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any]
    safe_error: str | None
    created_at: datetime
