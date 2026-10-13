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
    app_version: str = "2.0.0"
    git_sha: str = ""
    enable_api_docs: bool = True
    cors_origins: str = (
        "http://localhost:8015,http://localhost:8017,"
        "http://127.0.0.1:8015,http://127.0.0.1:8017"
    )

    database_url: str = "postgresql+psycopg://postgres:change-me@127.0.0.1:5432/neorvion_knowledge"
    test_database_url: str = (
        "postgresql+psycopg://postgres:change-me@127.0.0.1:5432/neorvion_knowledge_test"
    )

    erp_jwt_secret: str = "change-me-in-local-dev"
    erp_jwt_algorithm: str = "HS256"
    erp_api_base_url: str = "http://127.0.0.1:8011"
    erp_internal_service_key: str = ""
    identity_cache_ttl_seconds: int = 30

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
