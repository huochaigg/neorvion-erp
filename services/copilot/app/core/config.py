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
    app_version: str = "15.0.0"
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
    iam_service_token_url: str = "http://127.0.0.1:8010/api/v1/service-tokens"
    insight_service_id: str = ""
    insight_service_secret: SecretStr = SecretStr("")
    evaluation_service_id: str = ""
    evaluation_service_secret: SecretStr = SecretStr("")
    database_url: str
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: float = 3.0
    database_connect_timeout_seconds: int = 3
    database_statement_timeout_ms: int = 5000
    conversation_page_size_max: int = 100
    conversation_context_tokens: int = 6000
    stale_run_seconds: int = 900
    chat_heartbeat_seconds: int = 10
    chat_lease_seconds: int = 90
    chat_reconcile_interval_seconds: int = 30
    chat_execution_timeout_seconds: int = 300
    chat_event_log_max: int = 2000
    chat_ui_progress_timeout_seconds: int = 30
    chat_sse_max_reconnect_attempts: int = 5
    chat_sse_max_reconnect_duration_seconds: int = 60
    copilot_debug_execution: bool = False
    copilot_debug_disable_execution_timeout: bool = False
    copilot_debug_disable_lease_recovery: bool = False

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
    evaluation_queue_key: str = "copilot:evaluations:v1"
    evaluation_lease_seconds: int = 60
    evaluation_worker_poll_seconds: int = 3
    evaluation_max_concurrency: int = 2
    evaluation_task_success_regression_threshold: float = 0.02
    evaluation_latency_regression_threshold: float = 0.20
    evaluation_token_regression_threshold: float = 0.20
    evaluation_trace_retention_days: int = 90
    insight_scheduler_enabled: bool = False
    insight_queue_key: str = "copilot:insights:v1"
    insight_worker_poll_seconds: int = 3
    insight_lease_seconds: int = 60
    insight_max_concurrency: int = 2
    insight_max_attempts: int = 3
    quota_enforcement_enabled: bool = False
    budget_max_model_calls_per_request: int = 12
    mcp_remote_execution_enabled: bool = False
    mcp_allowed_hosts: str = ""
    mcp_egress_proxy_url: str = ""
    mcp_network_isolation_acknowledged: bool = False
    mcp_budget_gate_verified: bool = False
    mcp_origin: str = "https://copilot.neorvion.invalid"
    mcp_timeout_seconds: int = 15
    mcp_max_response_bytes: int = 262_144
    mcp_max_tools_per_server: int = 100
    skill_chat_enabled: bool = False
    skill_file_max_bytes: int = 65_536
    skill_reference_max_bytes: int = 32_768
    skill_resources_max_bytes: int = 65_536
    skill_resources_max_files: int = 8
    skill_context_max_chars: int = 16_000
    skill_selector_mode: str = "LEGACY"
    skill_selector_top_k: int = 5
    skill_selector_recall_threshold: float = 0.08
    skill_selector_rule_threshold: float = 0.52
    skill_selector_semantic_threshold: float = 0.20
    skill_selector_ambiguity_margin: float = 0.08
    skill_selector_llm_enabled: bool = False
    skill_selector_llm_timeout_seconds: float = 8.0
    skill_selector_llm_confidence_threshold: float = 0.72
    skill_multi_enabled: bool = False
    skill_plan_max_steps: int = 4
    skill_plan_max_total_tokens: int = 12_000
    skill_plan_timeout_seconds: float = 60.0
    skill_pending_enabled: bool = True
    skill_pending_ttl_seconds: int = 900
    skill_business_timezone: str = "Asia/Shanghai"
    skill_evaluation_enabled: bool = False
    skill_evaluation_e2e_enabled: bool = False
    intent_v15_mode: str = "DISABLED"
    intent_classifier_llm_enabled: bool = True
    intent_shadow_llm_enabled: bool = False
    intent_classifier_timeout_seconds: float = 6.0
    intent_classifier_model: str = ""
    intent_pending_ttl_seconds: int = 900
    intent_context_max_messages: int = 8
    intent_evaluation_enabled: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() in {"test", "testing"}

    def debug_execution_enabled(self) -> bool:
        """开发机允许断点长时间暂停；测试与生产默认关闭，禁止由客户端开启。"""
        if self.is_production:
            return False
        if self.copilot_debug_execution or self.copilot_debug_disable_lease_recovery:
            return True
        return self.app_env.lower() in {"development", "dev"}

    def hold_stale_lease_for_instance(self) -> bool:
        """同一进程心跳变慢时是否仍视为存活。断点会卡住事件循环，不能当孤儿回收。"""
        if self.is_production or self.is_test:
            return self.copilot_debug_disable_lease_recovery
        return True

    def execution_timeout_enabled(self) -> bool:
        if self.is_production:
            return True
        if self.copilot_debug_disable_execution_timeout or self.debug_execution_enabled():
            return False
        return True

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def mcp_allowed_host_list(self) -> list[str]:
        return [
            item.strip().lower().rstrip(".")
            for item in self.mcp_allowed_hosts.split(",")
            if item.strip()
        ]

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
        if not self.quota_enforcement_enabled:
            raise RuntimeError("生产环境必须启用 QUOTA_ENFORCEMENT_ENABLED")
        if (
            self.copilot_debug_execution
            or self.copilot_debug_disable_execution_timeout
            or self.copilot_debug_disable_lease_recovery
        ):
            raise RuntimeError("生产环境禁止开启 Copilot 调试超时豁免")
        if self.mcp_remote_execution_enabled and (
            not self.mcp_allowed_host_list
            or not self.mcp_network_isolation_acknowledged
            or not self.mcp_budget_gate_verified
            or not self.mcp_egress_proxy_url.strip()
        ):
            raise RuntimeError("生产 MCP 必须配置网络隔离并确认预算硬门禁已验收")


@lru_cache
def get_settings() -> Settings:
    # 必填项来自环境变量 / .env；构造函数静态类型看不到这些来源。
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
