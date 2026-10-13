from functools import lru_cache

from app.ai.mock import MockChatClient, MockEmbeddingClient, MockRerankClient
from app.ai.openai_compat import (
    OpenAICompatChatClient,
    OpenAICompatEmbeddingClient,
    OpenAICompatRerankClient,
)
from app.ai.types import ChatClient, EmbeddingClient, RerankClient
from app.core.config import settings


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    if settings.model_provider == "mock":
        return MockEmbeddingClient()
    return OpenAICompatEmbeddingClient(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
    )


@lru_cache
def get_chat_client() -> ChatClient:
    if settings.model_provider == "mock":
        return MockChatClient()
    return OpenAICompatChatClient(
        base_url=settings.chat_base_url,
        api_key=settings.chat_api_key,
        model=settings.chat_model,
    )


@lru_cache
def get_rerank_client() -> RerankClient | None:
    if settings.model_provider == "mock":
        return MockRerankClient()
    if not settings.rerank_api_key or not settings.rerank_model:
        return None
    return OpenAICompatRerankClient(
        base_url=settings.rerank_base_url or settings.chat_base_url,
        api_key=settings.rerank_api_key,
        model=settings.rerank_model,
    )
