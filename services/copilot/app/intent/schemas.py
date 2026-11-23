"""意图理解层的结构化契约。这些对象只描述理解结果，不构成授权。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProblemType = Literal["QUERY", "ACTION", "GUIDE", "ANALYZE", "CHAT", "UNKNOWN"]
IntentDomain = Literal[
    "GENERAL",
    "INVENTORY",
    "SALES",
    "PROCUREMENT",
    "KNOWLEDGE",
    "WORKFLOW",
    "PRODUCT",
    "PARTY",
]
IntentDecision = Literal["CLEAR", "AMBIGUOUS", "INSUFFICIENT", "UNKNOWN"]
ClassifierMethod = Literal["DISABLED", "RULES", "LLM", "HYBRID", "PENDING", "FALLBACK"]
RiskHint = Literal["READ_ONLY", "DRAFT_WRITE", "APPROVAL_REQUIRED", "HIGH_RISK", "UNIMPLEMENTED"]
ContextSource = Literal[
    "current_message",
    "recent_user_message",
    "recent_assistant_message",
    "tool_result",
    "pending_skill",
    "pending_intent",
    "pending_proposal",
    "inferred",
]


class SlotSpec(BaseModel):
    """单个槽位定义；校验发生在服务端，模型不能改写必填规则。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=200)
    required: bool = False


class IntentDefinition(BaseModel):
    """Registry 中的意图定义。intent 是业务目标，不等于 Agent/Skill/Tool。"""

    model_config = ConfigDict(extra="forbid")

    intent_key: str = Field(pattern=r"^[a-z][a-z0-9_.]{2,63}$")
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=400)
    domain: IntentDomain
    problem_type: ProblemType
    examples: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()
    required_slots: tuple[str, ...] = ()
    optional_slots: tuple[str, ...] = ()
    candidate_agents: tuple[str, ...] = ()
    candidate_skills: tuple[str, ...] = ()
    capability_hints: tuple[str, ...] = ()
    risk_hint: RiskHint = "READ_ONLY"
    executable: bool = True
    enabled: bool = True

    @field_validator("required_slots", "optional_slots")
    @classmethod
    def unique_slots(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("slot 名称不能重复")
        return value


class ExtractedSlot(BaseModel):
    name: str
    value: str
    source: ContextSource = "current_message"
    confidence: float = Field(default=1.0, ge=0, le=1)


class IntentCandidate(BaseModel):
    intent_key: str
    problem_type: ProblemType
    domain: IntentDomain
    score: float = Field(ge=0, le=1)
    signals: tuple[str, ...] = ()
    slots: tuple[ExtractedSlot, ...] = ()
    missing_slots: tuple[str, ...] = ()
    source: ClassifierMethod = "RULES"


class ResolvedTask(BaseModel):
    """一条被保留的用户任务；多任务时不要压成单个 Intent。"""

    task_id: str
    intent_key: str
    name: str
    problem_type: ProblemType
    domain: IntentDomain
    slots: dict[str, str] = Field(default_factory=dict)
    missing_slots: tuple[str, ...] = ()
    candidate_agents: tuple[str, ...] = ()
    candidate_skills: tuple[str, ...] = ()
    capability_hints: tuple[str, ...] = ()
    risk_hint: RiskHint = "READ_ONLY"
    executable: bool = True
    depends_on: tuple[str, ...] = ()
    parallel_group: int = 0
    source: ClassifierMethod = "RULES"


class ContextEntity(BaseModel):
    name: str
    value: str
    source: ContextSource
    trusted: bool
    expires_in_turns: int = 6


class ConversationContext(BaseModel):
    """按 tenant/user/conversation 隔离的轻量上下文，不是长期记忆。"""

    tenant_id: int
    user_id: int
    conversation_id: int | None = None
    current_text: str
    recent_user_texts: tuple[str, ...] = ()
    recent_assistant_texts: tuple[str, ...] = ()
    entities: tuple[ContextEntity, ...] = ()
    pending_intent_key: str | None = None
    pending_slots: dict[str, str] = Field(default_factory=dict)
    pending_missing: tuple[str, ...] = ()
    pending_skill_key: str | None = None
    has_open_proposal: bool = False
    anaphora: bool = False
    context_dependent: bool = False
    refs: tuple[str, ...] = ()


class ClassificationResult(BaseModel):
    method: ClassifierMethod
    problem_types: tuple[ProblemType, ...]
    candidates: tuple[IntentCandidate, ...]
    negative_action: bool = False
    how_to: bool = False
    multi_task: bool = False
    unknown: bool = False
    llm_called: bool = False
    llm_usage: dict[str, Any] | None = None
    fallback_reason: str | None = None
    raw_error: str | None = None


class RoutingPlan(BaseModel):
    """理解层给执行层的建议；IAM / ToolExecutor 仍可否决。"""

    agent_mode: Literal["single", "multi", "workflow"] = "single"
    agents: tuple[str, ...] = ()
    skill_policy: Literal["SKIP", "CANDIDATE", "EXPLICIT", "MULTI"] = "SKIP"
    skill_keys: tuple[str, ...] = ()
    forbid_skill_keys: tuple[str, ...] = ()
    allow_multi_agent: bool = True
    clarify: bool = False
    pending: bool = False
    reason: str = ""


class ToolPolicy(BaseModel):
    """服务端工具门禁。分类 CLEAR 也不等于允许写。"""

    allow_propose_action: bool = False
    blocked_tools: tuple[str, ...] = ()
    reason: str = "默认禁止因分类结果扩大写权限"


class IntentResolution(BaseModel):
    """一次理解的完整结果，供 Chat、评测和 Trace 复用。"""

    resolution_id: str
    feature_mode: Literal["DISABLED", "SHADOW", "ENABLED"]
    applied: bool
    classifier_method: ClassifierMethod
    problem_types: tuple[ProblemType, ...] = ()
    candidate_intents: tuple[str, ...] = ()
    resolved_intents: tuple[str, ...] = ()
    tasks: tuple[ResolvedTask, ...] = ()
    decision: IntentDecision = "UNKNOWN"
    missing_slots: tuple[str, ...] = ()
    context_refs: tuple[str, ...] = ()
    routing_plan: RoutingPlan = Field(default_factory=RoutingPlan)
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    public_status: str = ""
    clarification: str | None = None
    pending: bool = False
    cancel_pending: bool = False
    negative_action: bool = False
    fallback_reason: str | None = None
    latency_ms: float = 0
    model_usage: dict[str, Any] | None = None
    llm_called: bool = False
    error_code: int | None = None
    trace: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        """普通 Chat UI 只展示摘要，不返回内部 JSON 或模型推理。"""
        return {
            "resolution_id": self.resolution_id,
            "status_text": self.public_status,
            "decision": self.decision,
            "intents": list(self.resolved_intents),
            "problem_types": list(self.problem_types),
            "missing_slots": list(self.missing_slots),
            "pending": self.pending,
            "clarification": self.clarification,
            "agents": list(self.routing_plan.agents),
            "skills": list(self.routing_plan.skill_keys),
            "mode": self.routing_plan.agent_mode,
        }

    def diagnostic_payload(self) -> dict[str, Any]:
        """开发者/评测视图使用；仍不含 Prompt 原文和模型思维链。"""
        return {
            **self.public_payload(),
            "feature_mode": self.feature_mode,
            "applied": self.applied,
            "classifier_method": self.classifier_method,
            "candidate_intents": list(self.candidate_intents),
            "fallback_reason": self.fallback_reason,
            "latency_ms": self.latency_ms,
            "llm_called": self.llm_called,
            "model_usage": self.model_usage,
            "error_code": self.error_code,
            "tool_policy": self.tool_policy.model_dump(),
            "routing_plan": self.routing_plan.model_dump(),
            "context_refs": list(self.context_refs),
            "negative_action": self.negative_action,
        }
