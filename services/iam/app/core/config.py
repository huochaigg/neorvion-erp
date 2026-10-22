from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """IAM 配置。JWT 签名密钥与 RSA 传输密钥必须独立；生产缺密钥拒绝启动。"""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Neorvion IAM"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8010
    app_version: str = "2.0.0"
    git_sha: str = ""
    enable_api_docs: bool = True

    jwt_issuer: str = "neorvion-iam"
    jwt_audiences: str = "neorvion-iam,neorvion-erp,neorvion-knowledge,neorvion-copilot"
    jwt_key_id: str = "jwt-v1"
    jwt_private_key_path: str = "secrets/jwt/v1/private.pem"
    jwt_public_key_path: str = "secrets/jwt/v1/public.pem"
    jwt_previous_key_id: str = ""
    jwt_previous_private_key_path: str = ""
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7
    jwt_leeway_seconds: int = 10

    cors_origins: str = (
        "http://localhost:8015,http://localhost:8016,http://localhost:8017,http://localhost:8018,"
        "http://127.0.0.1:8015,http://127.0.0.1:8016,http://127.0.0.1:8017,http://127.0.0.1:8018"
    )

    refresh_cookie_name: str = "neorvion_refresh"
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_samesite: str = "lax"
    refresh_cookie_secure: bool = False
    csrf_cookie_name: str = "neorvion_csrf"
    csrf_cookie_path: str = "/"
    snapshot_ttl_seconds: int = 3600

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "neorvion"
    mysql_password: str = "neorvion_dev"
    mysql_database: str = "neorvion_iam"
    mysql_test_database: str = "neorvion_iam_test"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 1

    rsa_key_id: str = "v1"
    rsa_private_key_path: str = "secrets/rsa/v1/private.pem"
    rsa_public_key_path: str = "secrets/rsa/v1/public.pem"
    rsa_previous_key_id: str = ""
    rsa_previous_private_key_path: str = ""
    rsa_challenge_ttl_seconds: int = 300

    permission_sync_key: str = ""
    internal_service_key: str = ""
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    def access_token_ttl_seconds(self) -> int:
        return self.jwt_access_expire_minutes * 60

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def jwt_audience_list(self) -> list[str]:
        return [item.strip() for item in self.jwt_audiences.split(",") if item.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
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

    def require_runtime_secrets(self) -> None:
        """生产环境缺少 JWT / RSA 密钥文件时拒绝启动。"""
        jwt_private = _BACKEND_DIR / self.jwt_private_key_path
        rsa_private = _BACKEND_DIR / self.rsa_private_key_path
        if self.is_production:
            missing: list[str] = []
            if not jwt_private.is_file():
                missing.append("JWT_PRIVATE_KEY_PATH")
            if not rsa_private.is_file():
                missing.append("RSA_PRIVATE_KEY_PATH")
            if not self.jwt_issuer or not self.jwt_audience_list:
                missing.append("JWT_ISSUER/JWT_AUDIENCES")
            if missing:
                joined = "、".join(missing)
                raise RuntimeError(f"生产环境缺少 IAM 密钥配置：{joined}")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.require_runtime_secrets()
    return settings


settings = get_settings()
