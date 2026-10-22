from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=128, description="会话标题")


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=128, description="新的会话标题")


class ConversationMessageIn(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64, description="客户端生成的幂等请求 ID")
    message: str = Field(min_length=1, max_length=4000, description="本轮用户消息")


class ToolRunOut(BaseModel):
    id: int = Field(description="工具运行记录 ID")
    message_id: int = Field(description="关联的助手消息 ID")
    tool_call_id: str = Field(description="模型生成的本轮工具调用 ID")
    tool_name: str = Field(description="服务端白名单中的工具名称")
    status: str = Field(description="RUNNING、SUCCEEDED、FAILED 或 CANCELLED")
    duration_ms: int | None
    input_summary: str | None
    output_summary: str | None
    error_code: int | None
    created_at: datetime
    completed_at: datetime | None


class MessageOut(BaseModel):
    id: int = Field(description="消息 ID")
    role: str = Field(description="面向用户的 user 或 assistant 角色")
    content: str
    status: str = Field(description="本轮生成状态")
    request_id: str = Field(description="服务端生成的稳定运行 ID")
    created_at: datetime
    updated_at: datetime
    tool_runs: list[ToolRunOut] = Field(default_factory=list)


class ConversationOut(BaseModel):
    id: int
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class ConversationListOut(BaseModel):
    items: list[ConversationOut]
    total: int
    page: int
    page_size: int
