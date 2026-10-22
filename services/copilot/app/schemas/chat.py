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
        min_length=1,
        description="本次请求携带的有限上下文，最后一条必须是 user",
    )

    @model_validator(mode="after")
    def validate_context(self) -> "ChatRequest":
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
                raise ValueError(
                    f"单条消息长度不能超过 {settings.chat_max_message_chars} 字符"
                )
            item.content = text
            total += len(text)
        if total > settings.chat_max_context_chars:
            raise ValueError(f"上下文总长度不能超过 {settings.chat_max_context_chars} 字符")
        return self


class TokenUsageOut(BaseModel):
    prompt_tokens: int | None = Field(default=None, description="供应商返回的输入 Token；未知时为空")
    completion_tokens: int | None = Field(
        default=None,
        description="供应商返回的输出 Token；未知时为空",
    )


class ChatResponse(BaseModel):
    answer: str
    model: str
    usage: TokenUsageOut | None = None

