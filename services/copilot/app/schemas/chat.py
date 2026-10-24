from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.config import settings


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"] = Field(
        description="客户端历史消息角色；system 只允许由服务端注入",
    )
    content: str = Field(min_length=1, description="消息正文")


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(
        default_factory=list,
        description="本次请求携带的有限上下文，最后一条必须是 user",
    )
    conversation_id: int | None = Field(default=None, gt=0, description="持久化会话 ID")
    client_request_id: str | None = Field(
        default=None, min_length=8, max_length=64, description="客户端生成的幂等请求 ID"
    )
    message: str | None = Field(
        default=None, min_length=1, max_length=4000, description="持久化会话中的本轮用户消息"
    )

    @model_validator(mode="after")
    def validate_context(self) -> "ChatRequest":
        if self.conversation_id is not None:
            if not self.client_request_id or not self.message or not self.message.strip():
                raise ValueError("持久化会话必须提供 client_request_id 和 message")
            self.message = self.message.strip()
            return self
        if not self.messages:
            raise ValueError("无会话模式必须提供 messages")
        if len(self.messages) > settings.chat_max_messages:
            raise ValueError(f"消息数量不能超过 {settings.chat_max_messages}")
        if self.messages[-1].role != "user":
            raise ValueError("最后一条消息必须是 user")
        total = 0
        for item in self.messages:
            text = item.content.strip()
            if not text:
                raise ValueError("消息正文不能为空")
            if len(text) > settings.chat_max_message_chars:
                raise ValueError(f"单条消息长度不能超过 {settings.chat_max_message_chars} 字符")
            item.content = text
            total += len(text)
        if total > settings.chat_max_context_chars:
            raise ValueError(f"上下文总长度不能超过 {settings.chat_max_context_chars} 字符")
        return self


class TokenUsageOut(BaseModel):
    prompt_tokens: int | None = Field(
        default=None, description="供应商返回的输入 Token；未知时为空"
    )
    completion_tokens: int | None = Field(
        default=None,
        description="供应商返回的输出 Token；未知时为空",
    )


class ChatResponse(BaseModel):
    answer: str
    model: str
    usage: TokenUsageOut | None = None
    conversation_id: int | None = None
    message_id: int | None = None
    request_id: str | None = None
