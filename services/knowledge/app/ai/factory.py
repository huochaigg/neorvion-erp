from functools import lru_cache

from app.ai.dashscope import DashScopeRerankClient
from app.ai.mock import MockChatClient, MockEmbeddingClient, MockRerankClient
from app.ai.openai_compat import (
    OpenAICompatChatClient,
    OpenAICompatEmbeddingClient,
    OpenAICompatRerankClient,
)
from app.ai.types import ChatClient, EmbeddingClient, RerankClient
from app.core.config import settings
from app.core.exceptions import AppError


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    if settings.resolved_provider("embedding") == "mock":
        return MockEmbeddingClient()
    base_url = settings.resolved_embedding_base_url()
    if not base_url:
        raise AppError("未配置 Embedding Base URL", code=50360, status_code=503)
    return OpenAICompatEmbeddingClient(
        base_url=base_url,
        api_key=settings.resolved_embedding_api_key(),
        model=settings.embedding_model,
    )


@lru_cache
def get_chat_client() -> ChatClient:
    if settings.resolved_provider("chat") == "mock":
        return MockChatClient()
    return OpenAICompatChatClient(
        base_url=settings.resolved_chat_base_url(),
        api_key=settings.resolved_chat_api_key(),
        model=settings.chat_model,
    )


@lru_cache
def get_rerank_client() -> RerankClient | None:
    provider = settings.resolved_provider("rerank")
    if provider == "mock":
        return MockRerankClient()
    if not settings.rerank_model.strip():
        return None
    api_key = settings.resolved_rerank_api_key()
    if not api_key:
        return None
    base_url = settings.resolved_rerank_base_url()
    if provider == "dashscope":
        return DashScopeRerankClient(base_url=base_url, api_key=api_key, model=settings.rerank_model)
    if not base_url:
        return None
    return OpenAICompatRerankClient(base_url=base_url, api_key=api_key, model=settings.rerank_model)
