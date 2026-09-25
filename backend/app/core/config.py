from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，全部来自环境变量或 .env，禁止把密钥写死在代码中。"""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Neorvion ERP"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    secret_key: str = "change-me-in-local-dev"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    cors_origins: str = "http://localhost:5173,http://localhost:5174"

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "neorvion"
    mysql_password: str = "neorvion_dev"
    mysql_database: str = "neorvion_erp"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def database_url(self) -> str:
        password = quote_plus(self.mysql_password)
        user = quote_plus(self.mysql_user)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
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
