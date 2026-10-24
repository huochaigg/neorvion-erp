from functools import lru_cache

from app.ai.mock import MockChatAdapter
from app.ai.openai_compat import OpenAICompatChatAdapter
from app.ai.types import ChatAdapter
from app.core.config import settings
from app.core.exceptions import AppError


@lru_cache
def get_chat_adapter() -> ChatAdapter:
    provider = settings.model_provider.strip().lower()
    if provider == "mock":
        if settings.app_env.lower() not in {"test", "testing", "development", "dev"}:
            raise AppError("当前环境禁止 Mock 模型", code=50360, status_code=503)
        return MockChatAdapter()
    if provider != "openai_compat":
        raise AppError("不支持的模型 Provider", code=50061, status_code=500)
    return OpenAICompatChatAdapter(
        base_url=settings.chat_base_url,
        api_key=settings.resolved_chat_api_key(),
        model=settings.chat_model,
        timeout_seconds=settings.chat_timeout_seconds,
        max_output_tokens=settings.chat_max_output_tokens,
    )
