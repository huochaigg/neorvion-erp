from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis import ping_redis
from app.schemas.health import HealthCheckData

HealthStatus = Literal["ok", "unavailable"]


class HealthService:
    """探活 MySQL 与 Redis。依赖失败只标记状态，不抛出。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def check(self) -> HealthCheckData:
        return HealthCheckData(
            mysql=self._check_mysql(),
            redis="ok" if ping_redis() else "unavailable",
            worker="unavailable",
            milestone="V12",
            version=settings.app_version,
            git_sha=settings.git_sha,
        )

    def _check_mysql(self) -> HealthStatus:
        try:
            self.session.execute(text("SELECT 1"))
            return "ok"
        except Exception:
            return "unavailable"
