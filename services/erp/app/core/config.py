from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# 只读 services/erp/.env，避免仓库根目录给 Docker Compose 用的账号覆盖本地独立配置。
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
    app_version: str = "1.0.0"
    git_sha: str = ""
    enable_api_docs: bool = True
    cors_origins: str = (
        "http://localhost:8015,http://localhost:8016,http://localhost:8018,"
        "http://127.0.0.1:8015,http://127.0.0.1:8016,http://127.0.0.1:8018"
    )

    iam_jwt_issuer: str = "neorvion-iam"
    iam_jwt_audience: str = "neorvion-erp"
    iam_jwks_url: str = "http://127.0.0.1:8010/.well-known/jwks.json"
    iam_jwt_key_id: str = "jwt-v1"
    iam_jwt_public_key_path: str = ""
    iam_jwt_private_key_path: str = ""
    iam_snapshot_ttl_seconds: int = 3600
    iam_authorize_url: str = "http://127.0.0.1:8010/api/v1/internal/authorize"
    iam_internal_key: str = ""
    iam_redis_host: str = "127.0.0.1"
    iam_redis_port: int = 6379
    iam_redis_password: str = ""
    iam_redis_db: int = 1

    # 登录、刷新 Cookie 与 RSA 传输仍在 ERP。业务 JWT 校验走 IAM，不使用 secret_key。
    secret_key: str = "change-me-in-local-dev"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7
    refresh_cookie_name: str = "neorvion_refresh"
    refresh_cookie_path: str = "/api/v1/auth"
    cookie_samesite: str = "lax"
    cookie_secure: bool = False
    internal_service_key: str = ""
    rsa_key_id: str = "v1"
    rsa_private_key_path: str = "secrets/rsa/v1/private.pem"
    rsa_public_key_path: str = "secrets/rsa/v1/public.pem"
    rsa_previous_key_id: str = ""
    rsa_previous_private_key_path: str = ""
    rsa_challenge_ttl_seconds: int = 300

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

    export_dir: str = str(_BACKEND_DIR / "var" / "exports")

    def access_token_ttl_seconds(self) -> int:
        return self.jwt_access_expire_minutes * 60

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

    @property
    def iam_redis_url(self) -> str:
        """IAM 授权快照所在 Redis，与 ERP 任务队列库隔离。"""
        if self.iam_redis_password:
            password = quote_plus(self.iam_redis_password)
            return (
                f"redis://:{password}@{self.iam_redis_host}:"
                f"{self.iam_redis_port}/{self.iam_redis_db}"
            )
        return f"redis://{self.iam_redis_host}:{self.iam_redis_port}/{self.iam_redis_db}"

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
