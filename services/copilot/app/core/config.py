from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_COPILOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Copilot 配置。模型密钥只从环境变量或未入库的本地 .env 读取。"""

    model_config = SettingsConfigDict(
        env_file=_COPILOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Neorvion Copilot"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8013
    app_version: str = "2.0.0"
    git_sha: str = ""
    enable_api_docs: bool = True
    cors_origins: str = (
        "http://localhost:8015,http://localhost:8018,http://localhost:8019,"
        "http://127.0.0.1:8015,http://127.0.0.1:8018,http://127.0.0.1:8019"
    )

    iam_jwt_issuer: str = "neorvion-iam"
    iam_jwt_audience: str = "neorvion-copilot"
    iam_jwks_url: str = "http://127.0.0.1:8010/.well-known/jwks.json"
    iam_jwt_key_id: str = "jwt-v1"
    iam_jwt_public_key_path: str = ""
    iam_snapshot_ttl_seconds: int = 3600
    iam_redis_url: str = "redis://127.0.0.1:6379/1"
    iam_redis_connect_timeout_seconds: float = 1.5
    iam_redis_read_timeout_seconds: float = 1.5
    iam_auth_timeout_seconds: float = 4.0
    database_url: str
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: float = 3.0
    database_connect_timeout_seconds: int = 3
    database_statement_timeout_ms: int = 5000
    conversation_page_size_max: int = 100
    conversation_context_tokens: int = 6000
    stale_run_seconds: int = 900

    model_provider: str = "openai_compat"
    chat_base_url: str = "https://api.deepseek.com"
    chat_api_key: str = ""
    chat_model: str = "deepseek-chat"
    chat_timeout_seconds: float = 30.0
    chat_max_output_tokens: int = 1024
    chat_max_messages: int = 12
    chat_max_message_chars: int = 4000
    chat_max_context_chars: int = 12000
    graph_recursion_limit: int = 16
    erp_base_url: str = "http://127.0.0.1:8011"
    erp_jwt_audience: str = "neorvion-erp"
    erp_connect_timeout_seconds: float = 3.0
    erp_read_timeout_seconds: float = 10.0
    tool_max_rounds: int = 5
    tool_max_calls: int = 8
    tool_total_timeout_seconds: float = 30.0
    tool_max_result_chars: int = 12000
    tool_max_page_size: int = 50
    deepseek_api_key: str = ""
    dashscope_api_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        if self.is_production:
            return None
        return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

    def resolved_chat_api_key(self) -> str:
        return (self.chat_api_key or self.deepseek_api_key or self.dashscope_api_key).strip()

    def require_runtime_secrets(self) -> None:
        """生产环境缺少身份校验或模型配置时拒绝启动，避免静默降级。"""
        if not self.is_production:
            return
        if not self.iam_jwks_url.strip() and not self.iam_jwt_public_key_path.strip():
            raise RuntimeError("生产环境必须配置 IAM_JWKS_URL 或 IAM_JWT_PUBLIC_KEY_PATH")
        if self.model_provider != "mock" and not self.resolved_chat_api_key():
            raise RuntimeError("生产环境必须配置 Chat 模型密钥")


@lru_cache
def get_settings() -> Settings:
    # 必填项来自环境变量 / .env；构造函数静态类型看不到这些来源。
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
