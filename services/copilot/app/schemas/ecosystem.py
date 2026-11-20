from __future__ import annotations

import re
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


class SkillCatalogItemOut(BaseModel):
    skill_id: int
    version_id: int
    skill_key: str
    name: str
    description: str
    version: int
    category: str = Field(description="来自已发布 Metadata 的业务分类")
    required_permissions: list[str] = Field(description="当前用户已满足的运行权限提示")


class SkillCatalogOut(BaseModel):
    auto_available: bool = Field(description="当前 Feature Flag 是否允许 Chat AUTO")
    default_mode: Literal["AUTO", "NONE"]
    selector_profile: str
    items: list[SkillCatalogItemOut]
    query_latency_ms: float


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
    source_format: Literal["JSON_TEMPLATE", "SKILL_MD"] = "JSON_TEMPLATE"
    source_metadata: dict[str, Any] = Field(
        default_factory=dict, description="导入时固化的标准 Frontmatter；不参与运行时授权"
    )
    resources: dict[str, str] = Field(
        default_factory=dict, description="导入时固化的只读 Reference 快照，键为 Skill 内相对路径"
    )

    @field_validator("instructions")
    @classmethod
    def reject_executable_content(cls, value: str) -> str:
        lowered = value.lower()
        forbidden = ("```python", "```sql", "```bash", "subprocess", "os.system", "eval(")
        if any(item in lowered for item in forbidden):
            raise ValueError("Skill 不允许包含可执行代码或命令")
        return value

    @field_validator("resources")
    @classmethod
    def validate_resources(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 8 or sum(len(item.encode("utf-8")) for item in value.values()) > 65_536:
            raise ValueError("Skill Reference 数量或总大小超过限制")
        if any(
            not key.startswith("references/")
            or ".." in key.split("/")
            or key.startswith("/")
            for key in value
        ):
            raise ValueError("Skill Reference 路径非法")
        return value

    @field_validator("source_metadata")
    @classmethod
    def validate_source_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        dependencies = value.get("dependencies", [])
        if not isinstance(dependencies, list) or len(dependencies) > 10 or any(
            not isinstance(item, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,79}", item)
            for item in dependencies
        ):
            raise ValueError("Skill dependencies 必须是最多 10 个合法 Skill Key")
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
    agent_name: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{2,63}$",
        description="可选的已审核专业 Agent；必须属于 Skill allowed_agents",
    )


class SkillTemplateImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_keys: list[str] | None = Field(
        default=None,
        max_length=20,
        description="为空时导入全部内置模板；仅允许服务端已登记模板 Key",
    )


class SkillTemplateImportOut(BaseModel):
    skill_key: str
    skill_id: int
    version: int
    status: Literal["IMPORTED", "UNCHANGED", "PROTECTED"]


class SkillRollbackIn(BaseModel):
    version: int = Field(gt=0, description="要恢复的历史 Skill 版本号；恢复后仍需重新审核")


class SkillRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    skill_id: int
    skill_version: int
    user_id: int
    conversation_id: int | None = None
    message_id: int | None = None
    selection_method: str | None = None
    selection_snapshot: dict[str, Any] = Field(default_factory=dict)
    plan_id: int | None = None
    plan_step_key: str | None = None
    idempotency_key: str
    status: str
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any]
    safe_error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class SkillPlanStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    step_key: str
    position: int
    skill_id: int
    skill_version_id: int
    agent_name: str
    depends_on: list[str]
    input_snapshot: dict[str, Any]
    result_snapshot: dict[str, Any]
    status: str
    safe_error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class SkillPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    conversation_id: int
    message_id: int
    status: str
    classification: dict[str, Any]
    selection_snapshot: dict[str, Any]
    budget_snapshot: dict[str, Any]
    safe_error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    steps: list[SkillPlanStepOut] = Field(default_factory=list)


class SkillVersionDiffOut(BaseModel):
    skill_id: int
    from_version: int
    to_version: int
    changed_fields: list[str]
    instructions_diff: list[str]
