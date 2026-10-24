from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
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
    app_version: str = "8.0.0"
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
    erp_execution_timeout_seconds: float = 15.0
    erp_execution_secret: SecretStr = SecretStr("")
    erp_execution_authorization_ttl_seconds: int = 60
    confirmation_ttl_seconds: int = 300
    approval_ttl_seconds: int = 86400
    action_graph_enabled: bool = True
    knowledge_base_url: str = "http://127.0.0.1:8012"
    knowledge_jwt_audience: str = "neorvion-knowledge"
    knowledge_connect_timeout_seconds: float = 3.0
    knowledge_read_timeout_seconds: float = 12.0
    knowledge_top_k_max: int = 8
    knowledge_evidence_excerpt_chars: int = 600
    evidence_history_limit: int = 40
    knowledge_history_revalidation_timeout_seconds: float = 5.0
    tool_max_rounds: int = 5
    tool_max_calls: int = 8
    tool_total_timeout_seconds: float = 30.0
    tool_max_result_chars: int = 12000
    tool_max_page_size: int = 50
    deepseek_api_key: str = ""
    dashscope_api_key: str = ""
    workflow_queue_key: str = "copilot:workflows:v1"
    workflow_redis_url: str = "redis://127.0.0.1:6379/0"
    workflow_lease_seconds: int = 45
    workflow_max_attempts: int = 3
    workflow_max_steps: int = 16
    workflow_worker_poll_seconds: int = 3
    workflow_reconcile_max_attempts: int = 6
    multi_agent_enabled: bool = True
    multi_agent_max_agents: int = 4
    multi_agent_max_parallel: int = 3
    multi_agent_total_timeout_seconds: float = 45.0
    multi_agent_context_chars: int = 4000
    multi_agent_result_chars: int = 8000

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
        provider = self.model_provider.strip().lower()
        if provider == "mock" and self.app_env.lower() not in {
            "test",
            "testing",
            "development",
            "dev",
        }:
            raise RuntimeError("Mock 模型只允许显式测试或开发环境")
        if provider not in {"mock", "openai_compat"}:
            raise RuntimeError("MODEL_PROVIDER 仅支持 openai_compat 或显式开发 mock")
        if not self.is_production:
            return
        if not self.iam_jwks_url.strip() and not self.iam_jwt_public_key_path.strip():
            raise RuntimeError("生产环境必须配置 IAM_JWKS_URL 或 IAM_JWT_PUBLIC_KEY_PATH")
        if provider == "mock":
            raise RuntimeError("生产环境禁止使用 Mock 模型")
        if not self.resolved_chat_api_key():
            raise RuntimeError("生产环境必须配置 Chat 模型密钥")
        if len(self.erp_execution_secret.get_secret_value()) < 32:
            raise RuntimeError("生产环境必须配置至少 32 字节的 ERP_EXECUTION_SECRET")
        if not self.action_graph_enabled:
            raise RuntimeError("生产环境禁止关闭持久化 Action Execution Graph")


@lru_cache
def get_settings() -> Settings:
    # 必填项来自环境变量 / .env；构造函数静态类型看不到这些来源。
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
