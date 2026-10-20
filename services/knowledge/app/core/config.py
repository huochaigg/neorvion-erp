from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置，全部来自环境变量或 services/knowledge/.env，禁止把密钥写死在代码中。"""

    model_config = SettingsConfigDict(
        env_file=_KNOWLEDGE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Neorvion Knowledge"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8012
    app_version: str = "5.0.0"
    git_sha: str = ""
    enable_api_docs: bool = True
    cors_origins: str = (
        "http://localhost:8015,http://localhost:8017,http://localhost:8018,"
        "http://127.0.0.1:8015,http://127.0.0.1:8017,http://127.0.0.1:8018"
    )

    database_url: str = "postgresql+psycopg://postgres:change-me@127.0.0.1:5432/neorvion_knowledge"
    test_database_url: str = (
        "postgresql+psycopg://postgres:change-me@127.0.0.1:5432/neorvion_knowledge_test"
    )

    iam_jwt_issuer: str = "neorvion-iam"
    iam_jwt_audience: str = "neorvion-knowledge"
    iam_jwks_url: str = "http://127.0.0.1:8010/.well-known/jwks.json"
    iam_jwt_key_id: str = "jwt-v1"
    iam_jwt_public_key_path: str = ""
    iam_jwt_private_key_path: str = ""
    iam_snapshot_ttl_seconds: int = 3600
    iam_authorize_url: str = "http://127.0.0.1:8010/api/v1/internal/authorize"
    iam_internal_key: str = ""
    iam_redis_url: str = "redis://127.0.0.1:6379/1"

    redis_url: str = "redis://127.0.0.1:6379/0"
    storage_root: str = str(_KNOWLEDGE_DIR / "var" / "storage")
    task_executor: str = "redis"
    task_queue_key: str = "knowledge:tasks"
    worker_concurrency: int = 1
    max_upload_files: int = 10
    max_upload_bytes: int = 20 * 1024 * 1024
    chunk_size_min: int = 100
    chunk_size_max: int = 8000
    default_chunk_size: int = 800
    default_chunk_overlap: int = 120
    pdf_page_warn: int = 80

    # 全局开关：mock 仅测试。各能力可再单独指定 provider。
    model_provider: str = "openai_compat"
    chat_provider: str = "openai_compat"
    embedding_provider: str = "openai_compat"
    rerank_provider: str = "dashscope"

    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 16
    chat_base_url: str = "https://api.deepseek.com"
    chat_api_key: str = ""
    chat_model: str = "deepseek-flash"
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = "qwen3-rerank"
    dashscope_api_key: str = ""
    deepseek_api_key: str = ""
    model_timeout_seconds: float = 30.0
    embedding_max_retries: int = 2
    default_top_k: int = 8
    default_candidate_k: int = 24
    rrf_k: int = 60
    chat_history_turns: int = 4
    chat_max_context_chars: int = 6000
    eval_max_cases: int = 200
    eval_token_budget: int = 200000
    eval_prompt_token_usd: float = 0.0
    eval_completion_token_usd: float = 0.0
    eval_model_retries: int = 3
    eval_retry_base_seconds: float = 0.2
    eval_lease_seconds: int = 45
    eval_token_reserve: int = 1500
    eval_continue_on_error: bool = True
    api_key_rate_limit_per_minute: int = 60

    def resolved_provider(self, kind: str) -> str:
        if self.model_provider == "mock":
            return "mock"
        mapping = {
            "chat": self.chat_provider,
            "embedding": self.embedding_provider,
            "rerank": self.rerank_provider,
        }
        return (mapping.get(kind) or self.model_provider or "openai_compat").strip() or "openai_compat"

    def resolved_chat_api_key(self) -> str:
        return (self.chat_api_key or self.deepseek_api_key).strip()

    def resolved_embedding_api_key(self) -> str:
        return (self.embedding_api_key or self.dashscope_api_key).strip()

    def resolved_rerank_api_key(self) -> str:
        return (self.rerank_api_key or self.dashscope_api_key or self.embedding_api_key).strip()

    def resolved_chat_base_url(self) -> str:
        return (self.chat_base_url or "https://api.deepseek.com").rstrip("/")

    def resolved_embedding_base_url(self) -> str:
        return self.embedding_base_url.rstrip("/")

    def resolved_rerank_base_url(self) -> str:
        if self.rerank_base_url.strip():
            return self.rerank_base_url.rstrip("/")
        return self.embedding_base_url.rstrip("/")

    def chat_api_key_env(self) -> str:
        return "CHAT_API_KEY" if self.chat_api_key.strip() else "DEEPSEEK_API_KEY"

    def embedding_api_key_env(self) -> str:
        return "EMBEDDING_API_KEY" if self.embedding_api_key.strip() else "DASHSCOPE_API_KEY"

    def rerank_api_key_env(self) -> str:
        if self.rerank_api_key.strip():
            return "RERANK_API_KEY"
        if self.dashscope_api_key.strip():
            return "DASHSCOPE_API_KEY"
        return "EMBEDDING_API_KEY"

    def require_runtime_secrets(self) -> None:
        """生产环境必须配置 JWKS，禁止用空公钥启动。"""
        if not self.is_production:
            return
        if not self.iam_jwks_url and not self.iam_jwt_public_key_path:
            raise RuntimeError("生产环境必须配置 IAM_JWKS_URL 或 IAM_JWT_PUBLIC_KEY_PATH")
        if not self.iam_authorize_url or not self.iam_internal_key:
            raise RuntimeError("生产环境必须配置 IAM_AUTHORIZE_URL 与 IAM_INTERNAL_KEY")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        """开发环境允许本机任意端口，避免 localhost 与 127.0.0.1 被当成不同源。"""
        if self.is_production:
            return None
        return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
