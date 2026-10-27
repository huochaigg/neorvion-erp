from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentTaskInput(BaseModel):
    agent_name: str = Field(max_length=64, description="可信 Registry 中的 Agent 名称")
    task_id: str = Field(max_length=96, description="本次父运行内稳定的任务标识")
    query: str = Field(max_length=4000, description="仅包含该专业 Agent 必需的用户问题")


class AgentResult(BaseModel):
    agent_name: str = Field(description="产生结果的可信 Agent 名称")
    task_id: str = Field(description="父运行内稳定的 Agent 任务标识")
    status: Literal["SUCCEEDED", "FAILED", "DEGRADED"] = Field(description="Agent 任务终态")
    facts: list[str] = Field(default_factory=list, description="专业 Agent 确认的事实")
    findings: list[str] = Field(default_factory=list, description="基于证据得出的发现")
    recommendations: list[str] = Field(default_factory=list, description="只读分析建议")
    evidences: list[dict[str, Any]] = Field(
        default_factory=list, description="经服务端登记的结构化证据"
    )
    missing_information: list[str] = Field(
        default_factory=list, description="无法完成判断时缺失的信息"
    )
    warnings: list[str] = Field(default_factory=list, description="需要向用户披露的风险")
    error_code: int | None = Field(default=None, description="失败时的脱敏业务错误码")
    usage: dict[str, int | None] | None = Field(
        default=None, description="模型返回的实际 token 用量；提供方不返回时为空"
    )
    duration_ms: int = Field(description="Agent 任务端到端耗时，单位毫秒")
