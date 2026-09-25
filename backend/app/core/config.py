from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# 只读 backend/.env，避免仓库根目录给 Docker Compose 用的账号覆盖本地独立配置。
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置，全部来自环境变量或 .env，禁止把密钥写死在代码中。"""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Neorvion ERP"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8011
    secret_key: str = "change-me-in-local-dev"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7
    cors_origins: str = (
        "http://localhost:8015,http://localhost:8016,"
        "http://127.0.0.1:8015,http://127.0.0.1:8016"
    )

    refresh_cookie_name: str = "neorvion_refresh"
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_samesite: str = "lax"
    refresh_cookie_secure: bool = False

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "neorvion"
    mysql_password: str = "neorvion_dev"
    mysql_database: str = "neorvion_erp"
    mysql_test_database: str = "neorvion_erp_test"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

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

    @property
    def cookie_secure(self) -> bool:
        if self.is_production:
            return True
        return self.refresh_cookie_secure

    @property
    def cookie_samesite(self) -> str:
        value = self.refresh_cookie_samesite.lower()
        if self.cookie_secure is False and value == "none":
            return "lax"
        return value

    @property
    def database_url(self) -> str:
        return self.build_database_url(self.mysql_database)

    @property
    def test_database_url(self) -> str:
        return self.build_database_url(self.mysql_test_database)

    def build_database_url(self, database: str) -> str:
        password = quote_plus(self.mysql_password)
        user = quote_plus(self.mysql_user)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{database}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            password = quote_plus(self.redis_password)
            return f"redis://:{password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
